"""
信号发生器 — 生成测试用波形数据，支持按钮发送和定时器发送

波形类型: 正弦波、方波、三角波、锯齿波
输出格式: (np.ndarray, int) — 兼容示波器 V3 输入

端口:
  - data(object, int): (float32 一维数组, 采样间隔微秒)
"""

import numpy as np

from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QComboBox,
                              QDoubleSpinBox, QSpinBox, QPushButton,
                              QCheckBox, QLabel)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer

from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf, ConnNodeContentWidget
from nodeeditor.node_socket import LEFT_CENTER, RIGHT_CENTER


class SignalGeneratorContent(ConnNodeContentWidget):
    """信号发生器内容部件 — 波形配置 + 手动/定时发送"""

    data_ready = pyqtSignal(object, int)  # (np.ndarray, interval_us)

    WAVE_TYPES = ["正弦波", "方波", "三角波", "锯齿波"]

    def initUI(self):
        layout = QVBoxLayout(self)

        # ── 波形类型 ─────────────────────────────────────────
        row = QHBoxLayout()
        row.addWidget(QLabel("波形类型"))
        self.wave_type_combo = QComboBox(self)
        self.wave_type_combo.addItems(self.WAVE_TYPES)
        row.addWidget(self.wave_type_combo)
        layout.addLayout(row)

        # ── 频率 ─────────────────────────────────────────────
        row = QHBoxLayout()
        row.addWidget(QLabel("频率 (Hz)"))
        self.freq_spin = QDoubleSpinBox(self)
        self.freq_spin.setRange(0.01, 1_000_000.0)
        self.freq_spin.setDecimals(3)
        self.freq_spin.setValue(1000.0)
        self.freq_spin.setSuffix(" Hz")
        row.addWidget(self.freq_spin)
        layout.addLayout(row)

        # ── 采样间隔 + 包大小 ───────────────────────────────
        row = QHBoxLayout()
        row.addWidget(QLabel("采样间隔"))
        self.interval_spin = QDoubleSpinBox(self)
        self.interval_spin.setRange(0.1, 10_000_000.0)
        self.interval_spin.setDecimals(1)
        self.interval_spin.setValue(10.0)
        self.interval_spin.setSuffix(" µs")
        row.addWidget(self.interval_spin)
        row.addWidget(QLabel("包大小"))
        self.packet_size_spin = QSpinBox(self)
        self.packet_size_spin.setRange(1, 1_000_000)
        self.packet_size_spin.setValue(1024)
        row.addWidget(self.packet_size_spin)
        layout.addLayout(row)

        # ── 幅值 + 偏移 ─────────────────────────────────────
        row = QHBoxLayout()
        row.addWidget(QLabel("幅值"))
        self.amplitude_spin = QDoubleSpinBox(self)
        self.amplitude_spin.setRange(0.01, 100.0)
        self.amplitude_spin.setDecimals(3)
        self.amplitude_spin.setValue(1.0)
        self.amplitude_spin.setSuffix(" V")
        row.addWidget(self.amplitude_spin)
        row.addWidget(QLabel("偏移"))
        self.offset_spin = QDoubleSpinBox(self)
        self.offset_spin.setRange(-10.0, 10.0)
        self.offset_spin.setDecimals(3)
        self.offset_spin.setValue(0.0)
        self.offset_spin.setSuffix(" V")
        row.addWidget(self.offset_spin)
        layout.addLayout(row)

        # ── 手动发送按钮 ─────────────────────────────────────
        self.send_btn = QPushButton("发送", self)
        layout.addWidget(self.send_btn)

        # ── 定时器 ───────────────────────────────────────────
        row = QHBoxLayout()
        row.addWidget(QLabel("定时器间隔"))
        self.timer_interval_spin = QDoubleSpinBox(self)
        self.timer_interval_spin.setRange(0.01, 3600.0)
        self.timer_interval_spin.setDecimals(3)
        self.timer_interval_spin.setValue(1.0)
        self.timer_interval_spin.setSuffix(" s")
        row.addWidget(self.timer_interval_spin)
        layout.addLayout(row)

        self.timer_enable = QCheckBox("启用定时器", self)
        layout.addWidget(self.timer_enable)

        layout.addStretch()

        # ── 信号连接 ────────────────────────────────────────
        self.send_btn.clicked.connect(self._send)
        self.timer_enable.stateChanged.connect(self._onTimerEnableChanged)
        self.timer_interval_spin.valueChanged.connect(self._onTimerDurationChanged)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._send)

        # ── 样式 ────────────────────────────────────────────
        self.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                background-color: transparent;
            }
            QComboBox {
                background-color: #202020;
                color: #e0e0e0;
                border: 1px solid #404040;
                padding: 2px 4px;
                min-width: 100px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #e0e0e0;
                margin-right: 4px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: #e0e0e0;
                selection-background-color: #404040;
                outline: none;
            }
            QDoubleSpinBox, QSpinBox {
                background-color: #202020;
                color: #e0e0e0;
                border: 1px solid #404040;
                padding: 2px 4px;
            }
            QDoubleSpinBox::up-button, QSpinBox::up-button,
            QDoubleSpinBox::down-button, QSpinBox::down-button {
                border: none;
                background: transparent;
                width: 0px;
            }
            QPushButton {
                background-color: #202020;
                color: #e0e0e0;
                border: 1px solid #404040;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #303030;
            }
            QPushButton:pressed {
                background-color: #404040;
            }
            QCheckBox {
                color: #e0e0e0;
            }
        """)

        self.setNodeSize(320, 272)

    # ── 波形生成 ──────────────────────────────────────────────

    def _generate(self) -> np.ndarray:
        """根据当前控件参数生成波形数据"""
        freq = self.freq_spin.value()
        interval_us = self.interval_spin.value()
        packet_size = int(self.packet_size_spin.value())
        amplitude = self.amplitude_spin.value()
        offset = self.offset_spin.value()
        wave_type = self.wave_type_combo.currentText()

        dt_s = interval_us * 1e-6
        t = np.arange(packet_size, dtype=np.float64) * dt_s

        if wave_type == "正弦波":
            data = amplitude * np.sin(2 * np.pi * freq * t)
        elif wave_type == "方波":
            data = amplitude * np.where(
                np.sin(2 * np.pi * freq * t) >= 0, 1.0, -1.0
            )
        elif wave_type == "三角波":
            # 通过 arcsin(sin()) 实现标准三角波
            data = amplitude * (
                (2.0 / np.pi) * np.arcsin(np.sin(2 * np.pi * freq * t))
            )
        elif wave_type == "锯齿波":
            # 双极性锯齿波 [-1, 1)
            ft = freq * t
            data = amplitude * (2.0 * (ft - np.floor(ft + 0.5)))
        else:
            data = np.zeros(packet_size, dtype=np.float32)

        data = data.astype(np.float32)
        data += offset
        return data

    # ── 发送 ──────────────────────────────────────────────────

    def _send(self):
        """生成波形数据并发射"""
        data = self._generate()
        self.data_ready.emit(data, int(self.interval_spin.value()))

    # ── 定时器 ──────────────────────────────────────────────

    def _onTimerEnableChanged(self, state: int):
        if state == Qt.Checked:
            interval = int(
                max(self.timer_interval_spin.value(), 0.01) * 1000
            )
            self.timer.start(interval)
        else:
            self.timer.stop()

    def _onTimerDurationChanged(self, value: float):
        self.timer.stop()
        if self.timer_enable.isChecked():
            self.timer.start(int(max(value, 0.01) * 1000))

    # ── 生命周期 ────────────────────────────────────────────

    def cleanup(self):
        self.timer.stop()


@register_node()
class SignalGeneratorNode(ConnNode):
    """信号发生器节点

    生成测试用波形数据，输出格式兼容示波器 V3 的输入。

    端口:
        输出 data: (ndarray, interval_us) — 波形数据 + 采样间隔
    """

    tppath = ("数据源", "信号发生器")
    icon = "icons/emitter.png"
    name = "信号发生器"
    tooltip = ("生成正弦波/方波/三角波/锯齿波测试信号\n"
               "支持按钮发送和定时器自动发送")
    conn_title = "信号发生器"

    NodeContent_class = SignalGeneratorContent

    def __init__(self, scene):
        super().__init__(scene,
            signalsConf=[
                ConnSocketConf(
                    socketType=2,
                    key="data",
                    tooltip="输出波形数据 (ndarray, interval_us)",
                    name="波形",
                    argsType=(object, int)
                ),
            ]
        )
        self.registerSignal("data", self.content.data_ready)

    def initSettings(self) -> None:
        super().initSettings()
        self.output_socket_position = RIGHT_CENTER

    def serialize(self) -> dict:
        res = super().serialize()
        c = self.content
        res.update({
            "wave_type_index": c.wave_type_combo.currentIndex(),
            "frequency_hz": c.freq_spin.value(),
            "interval_us": c.interval_spin.value(),
            "packet_size": c.packet_size_spin.value(),
            "amplitude_v": c.amplitude_spin.value(),
            "offset_v": c.offset_spin.value(),
            "timer_enabled": c.timer_enable.isChecked(),
            "timer_interval_s": c.timer_interval_spin.value(),
        })
        return res

    def deserialize(self, data: dict, hashmap: dict | None = None,
                    restore_id: bool = True):
        res = super().deserialize(data, hashmap, restore_id)
        c = self.content

        # 波形类型（索引或向后兼容文本）
        wave_index = data.get("wave_type_index")
        if wave_index is not None:
            idx = int(wave_index)
            if 0 <= idx < len(c.WAVE_TYPES):
                c.wave_type_combo.setCurrentIndex(idx)
        else:
            wave_text = data.get("wave_type", "")
            if wave_text in c.WAVE_TYPES:
                c.wave_type_combo.setCurrentText(wave_text)

        c.freq_spin.setValue(data.get("frequency_hz", 1000.0))
        c.interval_spin.setValue(data.get("interval_us", 10.0))
        c.packet_size_spin.setValue(data.get("packet_size", 1024))
        c.amplitude_spin.setValue(data.get("amplitude_v", 1.0))
        c.offset_spin.setValue(data.get("offset_v", 0.0))
        c.timer_interval_spin.setValue(data.get("timer_interval_s", 1.0))
        c.timer_enable.setChecked(data.get("timer_enabled", False))
        return res
