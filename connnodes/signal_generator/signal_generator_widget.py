"""
信号发生器节点 — 生成多种波形并按协议编码为 QByteArray 输出

单线程，QTimer 驱动
支持波形类型：正弦波、方波、三角波、锯齿波
"""
import math
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel,
                             QDoubleSpinBox, QSpinBox, QPushButton,
                             QComboBox)
from PyQt5.QtCore import pyqtSignal, QByteArray, QTimer

from conn_base import ConnNodeContentWidget
from connnodes.waveform_protocol import encode_packet


WAVEFORM_TYPES = ["正弦波", "方波", "三角波", "锯齿波"]


def _sine(phase: float) -> float:
    return math.sin(2 * math.pi * phase)


def _square(phase: float) -> float:
    return 1.0 if phase < 0.5 else -1.0


def _triangle(phase: float) -> float:
    """三角波：phase=0→-1, 0.25→0, 0.5→1, 0.75→0, 1→-1"""
    return 4.0 * (phase if phase < 0.5 else 1.0 - phase) - 1.0


def _sawtooth(phase: float) -> float:
    """锯齿波：Phase=0→-1, linearly to 1 at phase=1"""
    return 2.0 * phase - 1.0


WAVEFORM_FUNCS = {
    "正弦波": _sine,
    "方波": _square,
    "三角波": _triangle,
    "锯齿波": _sawtooth,
}


class SignalGeneratorContent(ConnNodeContentWidget):
    """信号发生器内容部件"""
    dataOutput = pyqtSignal(QByteArray)

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # ── 波形类型 ──
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("波形:"))
        self._typeCombo = QComboBox()
        self._typeCombo.addItems(WAVEFORM_TYPES)
        self._typeCombo.setFixedWidth(120)
        self._typeCombo.setStyleSheet("""
            QComboBox {
                background-color: #202020;
                color: #e0e0e0;
                border: 1px solid #404040;
                padding: 2px 4px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #202020;
                color: #e0e0e0;
                selection-background-color: #005000;
            }
        """)
        type_row.addWidget(self._typeCombo)
        type_row.addStretch()
        layout.addLayout(type_row)

        # ── 参数行 ──
        def add_param(layout_, label, widget):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(widget)
            row.addStretch()
            layout_.addLayout(row)

        self._freqSpin = QDoubleSpinBox()
        self._freqSpin.setRange(0.1, 10000.0)
        self._freqSpin.setValue(1.0)
        self._freqSpin.setDecimals(2)
        self._freqSpin.setSuffix(" Hz")
        self._freqSpin.setFixedWidth(120)
        add_param(layout, "频率:", self._freqSpin)

        self._ampSpin = QDoubleSpinBox()
        self._ampSpin.setRange(0.01, 10000.0)
        self._ampSpin.setValue(1.0)
        self._ampSpin.setDecimals(2)
        self._ampSpin.setSuffix(" V")
        self._ampSpin.setFixedWidth(120)
        add_param(layout, "幅值:", self._ampSpin)

        self._sampleRateSpin = QSpinBox()
        self._sampleRateSpin.setRange(100, 100000)
        self._sampleRateSpin.setValue(1000)
        self._sampleRateSpin.setSuffix(" Hz")
        self._sampleRateSpin.setFixedWidth(120)
        add_param(layout, "采样率:", self._sampleRateSpin)

        self._packetSizeSpin = QSpinBox()
        self._packetSizeSpin.setRange(10, 5000)
        self._packetSizeSpin.setValue(100)
        self._packetSizeSpin.setSuffix(" 点/包")
        self._packetSizeSpin.setFixedWidth(120)
        add_param(layout, "包大小:", self._packetSizeSpin)

        # ── 控制 ──
        ctrl = QHBoxLayout()
        self._startBtn = QPushButton("启动")
        self._startBtn.setCheckable(True)
        self._startBtn.setFixedWidth(80)
        ctrl.addWidget(self._startBtn)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        layout.addStretch()

        # ── 定时器 ──
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._onTick)

        # ── 相位追踪 ──
        self._phase = 0.0

        # ── 信号 ──
        self._startBtn.clicked.connect(self._onStartClicked)
        self._freqSpin.valueChanged.connect(self._restartIfActive)
        self._sampleRateSpin.valueChanged.connect(self._restartIfActive)
        self._packetSizeSpin.valueChanged.connect(self._restartIfActive)
        self._typeCombo.currentIndexChanged.connect(self._restartIfActive)

        self.setStyleSheet("""
            QDoubleSpinBox, QSpinBox, QPushButton, QLabel {
                background-color: #202020;
                color: #e0e0e0;
                border: 1px solid #404040;
                padding: 2px 4px;
            }
            QPushButton:checked {
                background-color: #005000;
                color: #00ff00;
                border: 1px solid #00ff00;
            }
        """)

        self.resize(200, 240)

    # ── 槽 ──

    def _onStartClicked(self, checked):
        if checked:
            self._phase = 0.0
            self._timer.start(self._calcInterval())
            self._startBtn.setText("停止")
        else:
            self._timer.stop()
            self._startBtn.setText("启动")

    def _restartIfActive(self):
        if self._timer.isActive():
            self._phase = 0.0
            self._timer.start(self._calcInterval())

    def _calcInterval(self) -> int:
        """定时器间隔（ms），保证每包有 packet_size 个采样点"""
        sps = self._sampleRateSpin.value()
        n = self._packetSizeSpin.value()
        return max(int(n / sps * 1000), 1)

    def _onTick(self):
        freq = self._freqSpin.value()
        amp = self._ampSpin.value()
        sr = self._sampleRateSpin.value()
        n = self._packetSizeSpin.value()
        wave_func = WAVEFORM_FUNCS.get(
            self._typeCombo.currentText(), _sine
        )

        interval_us = int(1_000_000 / sr)

        data = []
        for _ in range(n):
            data.append(amp * wave_func(self._phase))
            self._phase += freq / sr
            if self._phase >= 1.0:
                self._phase -= 1.0

        self.dataOutput.emit(encode_packet(interval_us, data))

    def cleanup(self):
        self._timer.stop()
