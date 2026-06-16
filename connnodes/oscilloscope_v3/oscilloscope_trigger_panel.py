"""
示波器 V3 — TriggerPanel（触发控制面板）

QGroupBox 面板，包含触发相关的全部 UI 控件。

所有控件变更通过 Signal 对外通知，由 OscilloscopeContent
接收后转发到对应 ChannelWorker。
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                              QFormLayout, QGroupBox, QHBoxLayout,
                              QLabel, QSpinBox, QVBoxLayout, QWidget)


class TriggerPanel(QGroupBox):
    """触发控制面板

    信号:
        sig_enabled_changed(bool): 触发启用/禁用
        sig_edge_changed(str): 边沿选择 ("rising"/"falling"/"both")
        sig_upper_threshold_changed(float): 高阈值变更
        sig_lower_threshold_changed(float): 低阈值变更
        sig_debounce_changed(int): 消抖窗口变更
    """

    sig_enabled_changed = pyqtSignal(bool)
    sig_edge_changed = pyqtSignal(str)
    sig_upper_threshold_changed = pyqtSignal(float)
    sig_lower_threshold_changed = pyqtSignal(float)
    sig_debounce_changed = pyqtSignal(int)

    # ── 边沿选项映射 ────────────────────────────────────
    EDGE_MAP = {
        "rising": "上升沿",
        "falling": "下降沿",
        "both": "双沿",
    }
    EDGE_REVERSE_MAP = {v: k for k, v in EDGE_MAP.items()}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("触发系统", parent)
        self._setupUI()
        self._connectSignals()

    def _setupUI(self) -> None:
        layout = QVBoxLayout(self)

        # ── 启用 + 模式 行 ──────────────────────────
        row1 = QHBoxLayout()
        self.enabled_cb = QCheckBox("启用", self)
        self.mode_combo = QComboBox(self)
        self.mode_combo.addItems(["Auto", "Normal"])
        self.mode_combo.setToolTip("Auto: 始终更新; Normal: 仅触发时更新")
        row1.addWidget(self.enabled_cb)
        row1.addWidget(QLabel("模式", self))
        row1.addWidget(self.mode_combo)
        row1.addStretch()
        layout.addLayout(row1)

        # ── 参数表单 ──────────────────────────────
        form = QFormLayout()

        self.edge_combo = QComboBox(self)
        self.edge_combo.addItems(list(self.EDGE_MAP.values()))
        self.edge_combo.setToolTip("触发边沿")
        form.addRow("边沿:", self.edge_combo)

        self.upper_spin = QDoubleSpinBox(self)
        self.upper_spin.setRange(-1e6, 1e6)
        self.upper_spin.setValue(1.0)
        self.upper_spin.setSingleStep(0.1)
        self.upper_spin.setDecimals(1)
        self.upper_spin.setToolTip("高阈值")
        form.addRow("高阈值:", self.upper_spin)

        self.lower_spin = QDoubleSpinBox(self)
        self.lower_spin.setRange(-1e6, 1e6)
        self.lower_spin.setValue(-1.0)
        self.lower_spin.setSingleStep(0.1)
        self.lower_spin.setDecimals(1)
        self.lower_spin.setToolTip("低阈值")
        form.addRow("低阈值:", self.lower_spin)

        self.debounce_spin = QSpinBox(self)
        self.debounce_spin.setRange(0, 1000)
        self.debounce_spin.setValue(5)
        self.debounce_spin.setToolTip("消抖窗口（采样点数）")
        form.addRow("消抖:", self.debounce_spin)

        layout.addLayout(form)

    def _connectSignals(self) -> None:
        """连接内部信号 → 对外通知信号"""
        self.enabled_cb.stateChanged.connect(
            lambda state: self.sig_enabled_changed.emit(
                bool(state)))
        self.mode_combo.currentTextChanged.connect(
            lambda text: None)  # mode 通过序列化恢复，UI 对外只读暂不触发
        self.edge_combo.currentTextChanged.connect(
            lambda text: self.sig_edge_changed.emit(
                self.EDGE_REVERSE_MAP.get(text, "rising")))
        self.upper_spin.valueChanged.connect(
            self.sig_upper_threshold_changed.emit)
        self.lower_spin.valueChanged.connect(
            self.sig_lower_threshold_changed.emit)
        self.debounce_spin.valueChanged.connect(
            self.sig_debounce_changed.emit)

    # ── 状态同步（反序列化 / 从 Worker 加载） ────────

    def set_values(self, enabled: bool, edge: str,
                   upper: float, lower: float,
                   debounce: int, mode: str = "auto") -> None:
        """设置面板控件的值（不发射信号）"""
        self.enabled_cb.blockSignals(True)
        self.enabled_cb.setChecked(enabled)
        self.enabled_cb.blockSignals(False)

        edge_text = self.EDGE_MAP.get(edge, "上升沿")
        idx = self.edge_combo.findText(edge_text)
        if idx >= 0:
            self.edge_combo.blockSignals(True)
            self.edge_combo.setCurrentIndex(idx)
            self.edge_combo.blockSignals(False)

        self.upper_spin.blockSignals(True)
        self.upper_spin.setValue(upper)
        self.upper_spin.blockSignals(False)

        self.lower_spin.blockSignals(True)
        self.lower_spin.setValue(lower)
        self.lower_spin.blockSignals(False)

        self.debounce_spin.blockSignals(True)
        self.debounce_spin.setValue(debounce)
        self.debounce_spin.blockSignals(False)

        mode_idx = 0 if mode == "auto" else 1
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(mode_idx)
        self.mode_combo.blockSignals(False)
