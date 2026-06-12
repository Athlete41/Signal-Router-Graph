"""
信号发生器节点 — 生成多种波形并按协议编码为 QByteArray 输出

多线程：波形生成在工作线程执行，不阻塞主线程 UI
支持波形类型：正弦波、方波、三角波、锯齿波
"""
import math
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel,
                             QDoubleSpinBox, QSpinBox, QPushButton,
                             QComboBox)
from PyQt5.QtCore import (pyqtSignal, pyqtSlot, QByteArray, QTimer,
                          QObject, QThread, QMetaObject, Qt)
from conn_base import ConnNodeContentWidget
from conn_utils import ThreadManager
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


# ═══════════════════════════════════════════════════════════════════════
# 工作线程核心
# ═══════════════════════════════════════════════════════════════════════

class _SignalGenWorker(QObject):
    """信号发生器工作线程 — 波形生成+定时器"""

    dataReady = pyqtSignal(QByteArray)  # 跨线程发射到主线程

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._onTick)
        self._phase = 0.0

        # 参数（从主线程同步）
        self._wave_type = "正弦波"
        self._freq = 1.0
        self._amp = 1.0
        self._sample_rate = 1000
        self._packet_size = 100

    # ── 参数更新槽（主线程通过信号跨线程调用） ──────────

    @pyqtSlot(float)
    def setFreq(self, freq: float):
        self._freq = freq
        self._restartIfActive()

    @pyqtSlot(float)
    def setAmp(self, amp: float):
        self._amp = amp

    @pyqtSlot(int)
    def setSampleRate(self, rate: int):
        self._sample_rate = rate
        self._restartIfActive()

    @pyqtSlot(int)
    def setPacketSize(self, size: int):
        self._packet_size = size
        self._restartIfActive()

    @pyqtSlot(str)
    def setWaveType(self, wtype: str):
        self._wave_type = wtype
        self._restartIfActive()

    @pyqtSlot()
    def start(self):
        """启动定时器，相位归零"""
        self._phase = 0.0
        interval_ms, _ = self._calcTiming()
        self._timer.start(interval_ms)

    @pyqtSlot()
    def stop(self):
        """停止定时器"""
        self._timer.stop()

    # ── 内部 ───────────────────────────────────────────

    def _calcTiming(self):
        """计算定时器间隔(ms)和每包数据点数

        保证：
            - 最小间隔 16ms（防止高采样率下 QTimer 过载）
            - 数据速率与采样率匹配（间隔被压缩时放大包大小补偿）
        Returns:
            (interval_ms, packet_size)
        """
        sps = self._sample_rate
        target_n = self._packet_size
        ideal_ms = int(target_n / sps * 1000)
        min_ms = 16
        if ideal_ms >= min_ms:
            return ideal_ms, target_n
        scaled_n = int(sps * min_ms / 1000)
        return min_ms, max(scaled_n, 1)

    def _onTick(self):
        freq = self._freq
        amp = self._amp
        sr = self._sample_rate
        _, n = self._calcTiming()
        wave_func = WAVEFORM_FUNCS.get(self._wave_type, _sine)

        interval_us = int(1_000_000 / sr)

        data = []
        for _ in range(n):
            data.append(amp * wave_func(self._phase))
            self._phase += freq / sr
            if self._phase >= 1.0:
                self._phase -= 1.0

        self.dataReady.emit(encode_packet(interval_us, data))

    def _restartIfActive(self):
        """运行中参数变更 → 相位归零 + 重置定时器"""
        if self._timer.isActive():
            self._phase = 0.0
            interval_ms, _ = self._calcTiming()
            self._timer.start(interval_ms)


# ═══════════════════════════════════════════════════════════════════════
# 内容部件（主线程）
# ═══════════════════════════════════════════════════════════════════════

class SignalGeneratorContent(ConnNodeContentWidget):
    """信号发生器内容部件

    管理工作线程生命周期，UI 控件通过信号桥接与工作线程通信。
    """
    dataOutput = pyqtSignal(QByteArray)

    def initUI(self):
        # ── 工作线程初始化 ──
        self._worker = _SignalGenWorker()
        self._thread = QThread()
        self._thread.start()
        ThreadManager.instance().register_thread(self._thread)
        self._worker.moveToThread(self._thread)

        # ── UI 布局 ──
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

        # ── 信号连接 ──
        self._connectSignals()

        self.setStyleSheet("""
            QDoubleSpinBox, QSpinBox, QPushButton, QLabel {
                background-color: #202020;
                color: #e0e0e0;
                border: 1px solid #404040;
                padding: 2px 4px;
            }
            QDoubleSpinBox::up-button, QSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 18px;
                background-color: #353535;
                border: 1px solid #505050;
                border-left: none;
                border-bottom: none;
                border-top-right-radius: 3px;
            }
            QDoubleSpinBox::down-button, QSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 18px;
                background-color: #353535;
                border: 1px solid #505050;
                border-left: none;
                border-top: none;
                border-bottom-right-radius: 3px;
            }
            QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {
                width: 0;
                height: 0;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 5px solid white;
            }
            QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {
                width: 0;
                height: 0;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid white;
            }
            QPushButton:checked {
                background-color: #005000;
                color: #00ff00;
                border: 1px solid #00ff00;
            }
        """)

        self.resize(200, 240)

    def _connectSignals(self):
        """连接所有信号（主线程 ↔ 工作线程）"""
        # worker 数据 → 主线程输出端口
        self._worker.dataReady.connect(self._onDataReady)

        # UI 控件 → worker 参数（跨线程，AutoConnection）
        self._freqSpin.valueChanged.connect(self._worker.setFreq)
        self._ampSpin.valueChanged.connect(self._worker.setAmp)
        self._sampleRateSpin.valueChanged.connect(self._worker.setSampleRate)
        self._packetSizeSpin.valueChanged.connect(self._worker.setPacketSize)
        self._typeCombo.currentTextChanged.connect(self._worker.setWaveType)

        # 启动/停止
        self._startBtn.clicked.connect(self._onStartClicked)

    # ── 槽 ──

    def _onStartClicked(self, checked):
        if checked:
            QMetaObject.invokeMethod(
                self._worker, "start", Qt.QueuedConnection
            )
            self._startBtn.setText("停止")
        else:
            QMetaObject.invokeMethod(
                self._worker, "stop", Qt.QueuedConnection
            )
            self._startBtn.setText("启动")

    @pyqtSlot(QByteArray)
    def _onDataReady(self, data: QByteArray):
        """工作线程数据到达 → 转发到节点输出端口"""
        self.dataOutput.emit(data)

    def cleanup(self):
        """清理工作线程"""
        QMetaObject.invokeMethod(
            self._worker, "stop", Qt.BlockingQueuedConnection
        )
        self._worker.deleteLater()
        self._thread.quit()
        self._thread.wait(3000)
        self._thread.deleteLater()
