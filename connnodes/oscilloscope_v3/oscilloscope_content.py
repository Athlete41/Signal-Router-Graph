"""
示波器 V3 — OscilloscopeContent（内容部件）

主线程 UI 容器，管理:
    1. WaveformWidget（波形画板）
    2. 4 个 OscilloscopeSampler + QThread（每通道独立线程）
    3. 控制面板（采集/水平/垂直系统）
    4. TriggerPanel（触发面板）
    5. 底部操作栏（启动/暂停/清空 + 通道可见性）
"""

from __future__ import annotations

from PyQt5.QtCore import (QThread, Qt, pyqtSignal, pyqtSlot)
from PyQt5.QtGui import QColor, QIcon, QPixmap
from PyQt5.QtWidgets import (QCheckBox, QDoubleSpinBox, QFormLayout,
                              QGroupBox, QHBoxLayout, QPushButton,
                              QScrollBar, QSpinBox, QVBoxLayout, QWidget)

from conn_base import ConnNodeContentWidget
from conn_utils import ThreadManager

from .oscilloscope_sampler import OscilloscopeSampler
from .oscilloscope_trigger_panel import TriggerPanel
from .oscilloscope_widget import (CHANNEL_COLORS, WaveformWidget)


class OscilloscopeContent(ConnNodeContentWidget):
    """示波器 V3 内容部件

    初始创建 4 个通道 Worker（ch0-ch3），固定端口。
    节点在 __init__.py 中将输入端口注册信号直连到对应 Worker.writeData。
    """

    def __init__(self, node, parent: QWidget | None = None) -> None:
        # ── 状态（super().__init__ 前设置） ──
        self._workers: list[OscilloscopeSampler] = []
        self._threads: list[QThread] = []

        self._channel_visible: list[bool] = [True] * 4
        self._channel_colors: list[QColor] = CHANNEL_COLORS[:4]

        # 设置缓存（读写均在主线程，不涉及跨线程共享）
        self._fps = 30
        self._buffer_size = 1_000_000
        self._sample_rate_hz = 1000.0
        self._time_window_s = 1.0
        self._y_range = 10.0
        self._y_offset = 0.0
        self._line_width = 2
        self._started = False

        # ── 触发面板状态 ──
        self._trigger_enabled = False
        self._trigger_edge = "rising"
        self._trigger_mode = "auto"
        self._trigger_high = 1.0
        self._trigger_low = -1.0
        self._trigger_debounce = 5

        super().__init__(node, parent)

    # ═══════════════════════════════════════════════════════
    # initUI — 由 ConnNodeContentWidget.__init__ 调用
    # ═══════════════════════════════════════════════════════

    def initUI(self) -> None:
        """创建完整 UI + 启动 4 个通道工作线程"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ── 1. WaveformWidget ────────────────────────
        self._waveform = WaveformWidget(self, self)
        layout.addWidget(self._waveform, stretch=1)

        # ── 2. ScrollBar ─────────────────────────────
        self._scrollbar = QScrollBar(Qt.Horizontal, self)
        self._scrollbar.setMinimum(0)
        self._scrollbar.setMaximum(0)
        self._scrollbar.setValue(0)
        layout.addWidget(self._scrollbar)

        # ── 3. 控制面板 ──────────────────────────────
        control_row = QHBoxLayout()

        # 采集系统
        acq_group = QGroupBox("采集系统", self)
        acq_layout = QFormLayout(acq_group)

        self.fps_spin = QSpinBox(self)
        self.fps_spin.setRange(1, 120)
        self.fps_spin.setValue(30)
        self.fps_spin.setToolTip("帧率 (FPS)")
        acq_layout.addRow("FPS:", self.fps_spin)

        self.buffer_spin = QSpinBox(self)
        self.buffer_spin.setRange(100, 10_000_000)
        self.buffer_spin.setValue(1_000_000)
        self.buffer_spin.setSingleStep(100_000)
        self.buffer_spin.setToolTip("环形缓冲区容量（点数）")
        acq_layout.addRow("缓存:", self.buffer_spin)

        self.sample_rate_spin = QDoubleSpinBox(self)
        self.sample_rate_spin.setRange(1, 10_000_000)
        self.sample_rate_spin.setValue(1000.0)
        self.sample_rate_spin.setToolTip("采样率 (Hz)")
        acq_layout.addRow("采样率:", self.sample_rate_spin)

        control_row.addWidget(acq_group)

        # 水平系统
        horiz_group = QGroupBox("水平系统", self)
        horiz_layout = QFormLayout(horiz_group)

        self.time_window_spin = QDoubleSpinBox(self)
        self.time_window_spin.setRange(0.001, 100.0)
        self.time_window_spin.setValue(1.0)
        self.time_window_spin.setDecimals(3)
        self.time_window_spin.setSingleStep(0.1)
        self.time_window_spin.setToolTip("时间窗口（秒）")
        horiz_layout.addRow("时间窗口:", self.time_window_spin)

        control_row.addWidget(horiz_group)

        # 垂直系统
        vert_group = QGroupBox("垂直系统", self)
        vert_layout = QFormLayout(vert_group)

        self.y_range_spin = QDoubleSpinBox(self)
        self.y_range_spin.setRange(0.1, 1000.0)
        self.y_range_spin.setValue(10.0)
        self.y_range_spin.setDecimals(2)
        self.y_range_spin.setToolTip("Y 轴范围（峰峰值）")
        vert_layout.addRow("Y范围:", self.y_range_spin)

        self.y_offset_spin = QDoubleSpinBox(self)
        self.y_offset_spin.setRange(-500.0, 500.0)
        self.y_offset_spin.setValue(0.0)
        self.y_offset_spin.setDecimals(2)
        self.y_offset_spin.setToolTip("Y 轴偏移")
        vert_layout.addRow("Y偏移:", self.y_offset_spin)

        self.line_width_spin = QSpinBox(self)
        self.line_width_spin.setRange(1, 10)
        self.line_width_spin.setValue(2)
        self.line_width_spin.setToolTip("波形线宽（像素）")
        vert_layout.addRow("线宽:", self.line_width_spin)

        control_row.addWidget(vert_group)
        layout.addLayout(control_row)

        # ── 4. TriggerPanel ──────────────────────────
        self._trigger_panel = TriggerPanel(self)
        layout.addWidget(self._trigger_panel)

        # ── 5. 底部操作栏 ────────────────────────────
        bottom_row = QHBoxLayout()

        self.start_btn = QPushButton("启动", self)
        self.start_btn.setCheckable(True)
        self.start_btn.setToolTip("启动/停止波形采集")
        bottom_row.addWidget(self.start_btn)

        self.pause_btn = QPushButton("暂停", self)
        self.pause_btn.setCheckable(True)
        self.pause_btn.setToolTip("暂停/恢复（不丢失数据）")
        bottom_row.addWidget(self.pause_btn)

        self.clear_btn = QPushButton("清空", self)
        self.clear_btn.setToolTip("清空所有通道缓冲区")
        bottom_row.addWidget(self.clear_btn)

        bottom_row.addStretch()

        # 通道可见性勾选
        self._chk_boxes: list[QCheckBox] = []
        for i in range(4):
            color = self._channel_colors[i]
            pix = QPixmap(12, 12)
            pix.fill(color)
            chk = QCheckBox(f"CH{i}", self)
            chk.setChecked(True)
            self._chk_boxes.append(chk)
            bottom_row.addWidget(chk)

        layout.addLayout(bottom_row)

        # ── 创建 Worker + 线程 ────────────────────────
        self._initWorkers()

        # ── 信号连接 ─────────────────────────────────
        self._connectSignals()

        # self.resize(400, 500)

    # ═══════════════════════════════════════════════════════
    # Worker 初始化
    # ═══════════════════════════════════════════════════════

    def _initWorkers(self) -> None:
        """创建 4 个通道 Worker 和独立 QThread"""
        for i in range(4):
            worker = OscilloscopeSampler()
            thread = QThread()
            thread.start()
            ThreadManager.instance().register_thread(thread)
            worker.moveToThread(thread)

            # 初始配置（在 moveToThread 前调用，主线程安全）
            worker.set_buffer_size(self._buffer_size)

            self._workers.append(worker)
            self._threads.append(thread)

    # ═══════════════════════════════════════════════════════
    # 信号连接
    # ═══════════════════════════════════════════════════════

    def _connectSignals(self) -> None:
        """连接 UI 控件 → 内容槽 → Worker 信号"""

        # ── 画板阈值信号 → 内容转发 → Worker ──
        self._waveform.sig_upper_threshold_changed.connect(
            self._onUpperThresholdChanged)
        self._waveform.sig_lower_threshold_changed.connect(
            self._onLowerThresholdChanged)

        # ── 采集系统 ──
        self.fps_spin.valueChanged.connect(self._onFpsChanged)
        self.buffer_spin.valueChanged.connect(self._onBufferSizeChanged)
        self.sample_rate_spin.valueChanged.connect(
            self._onSampleRateChanged)

        # ── 水平系统 ──
        self.time_window_spin.valueChanged.connect(
            self._onTimeWindowChanged)

        # ── 垂直系统（直接更新画板） ──
        self.y_range_spin.valueChanged.connect(self._onYRangeChanged)
        self.y_offset_spin.valueChanged.connect(self._onYOffsetChanged)
        self.line_width_spin.valueChanged.connect(self._onLineWidthChanged)

        # ── 滚动条 ──
        self._scrollbar.valueChanged.connect(self._onScrollChanged)

        # ── 底部按钮 ──
        self.start_btn.toggled.connect(self._onStartToggled)
        self.pause_btn.toggled.connect(self._onPauseToggled)
        self.clear_btn.clicked.connect(self._onClearClicked)

        # ── 通道可见性 ──
        for i, chk in enumerate(self._chk_boxes):
            chk.stateChanged.connect(
                lambda state, idx=i: self._onChannelVisibilityChanged(
                    idx, bool(state)))

        # ── TriggerPanel ──
        self._trigger_panel.sig_enabled_changed.connect(
            self._onTriggerEnabledChanged)
        self._trigger_panel.sig_edge_changed.connect(
            self._onTriggerEdgeChanged)
        self._trigger_panel.sig_upper_threshold_changed.connect(
            self._onTriggerUpperChanged)
        self._trigger_panel.sig_lower_threshold_changed.connect(
            self._onTriggerLowerChanged)
        self._trigger_panel.sig_debounce_changed.connect(
            self._onTriggerDebounceChanged)

    # ═══════════════════════════════════════════════════════
    # 画板数据接口（paintEvent 中调用）
    # ═══════════════════════════════════════════════════════

    def iter_draw_channels(self):
        """遍历所有通道，生成 (worker, color, visible) 元组

        在 WaveformWidget.paintEvent 中调用，实时遍历不缓存。
        """
        for i in range(len(self._workers)):
            yield (self._workers[i],
                   self._channel_colors[i],
                   self._channel_visible[i])

    # ═══════════════════════════════════════════════════════
    # UI 槽函数
    # ═══════════════════════════════════════════════════════

    # ── 采集系统 ───────────────────────────────────────

    @pyqtSlot(int)
    def _onFpsChanged(self, fps: int) -> None:
        self._fps = fps
        self._waveform.set_fps(fps)
        for w in self._workers:
            w.sig_set_fps.emit(fps)

    @pyqtSlot(int)
    def _onBufferSizeChanged(self, size: int) -> None:
        self._buffer_size = size
        for w in self._workers:
            w.set_buffer_size(size)
            w.clear()

    @pyqtSlot(float)
    def _onSampleRateChanged(self, hz: float) -> None:
        self._sample_rate_hz = hz
        for w in self._workers:
            w.sig_set_sample_rate.emit(hz)

    # ── 水平系统 ───────────────────────────────────────

    @pyqtSlot(float)
    def _onTimeWindowChanged(self, s: float) -> None:
        self._time_window_s = s
        for w in self._workers:
            w.sig_set_time_window.emit(s)

    @pyqtSlot(int)
    def _onScrollChanged(self, offset: int) -> None:
        for w in self._workers:
            w.sig_set_scroll_offset.emit(offset)

    # ── 垂直系统 ───────────────────────────────────────

    @pyqtSlot(float)
    def _onYRangeChanged(self, r: float) -> None:
        self._y_range = r
        self._waveform.set_y_range(r)

    @pyqtSlot(float)
    def _onYOffsetChanged(self, offset: float) -> None:
        self._y_offset = offset
        self._waveform.set_y_offset(offset)

    @pyqtSlot(int)
    def _onLineWidthChanged(self, w: int) -> None:
        self._line_width = w
        self._waveform.set_line_width(w)

    # ── 运行控制 ───────────────────────────────────────

    @pyqtSlot(bool)
    def _onStartToggled(self, checked: bool) -> None:
        self._started = checked
        if checked:
            self.start_btn.setText("停止")
            for w in self._workers:
                w.sig_set_running.emit(True)
        else:
            self.start_btn.setText("启动")
            for w in self._workers:
                w.sig_set_running.emit(False)

    @pyqtSlot(bool)
    def _onPauseToggled(self, paused: bool) -> None:
        self.pause_btn.setText("继续" if paused else "暂停")
        for w in self._workers:
            w.sig_set_paused.emit(paused)

    @pyqtSlot()
    def _onClearClicked(self) -> None:
        for w in self._workers:
            w.clear()

    # ── 通道可见性 ────────────────────────────────────

    @pyqtSlot(int, bool)
    def _onChannelVisibilityChanged(self, idx: int,
                                    visible: bool) -> None:
        if 0 <= idx < len(self._channel_visible):
            self._channel_visible[idx] = visible

    # ── 触发 ──────────────────────────────────────────

    @pyqtSlot(bool)
    def _onTriggerEnabledChanged(self, enabled: bool) -> None:
        self._trigger_enabled = enabled
        for w in self._workers:
            w.sig_set_trigger_enabled.emit(enabled)

    @pyqtSlot(str)
    def _onTriggerEdgeChanged(self, edge: str) -> None:
        self._trigger_edge = edge
        for w in self._workers:
            w.sig_set_trigger_edge.emit(edge)

    @pyqtSlot(float)
    def _onTriggerUpperChanged(self, val: float) -> None:
        self._trigger_high = val
        self._waveform.set_thresholds(
            val, self._trigger_low, self._trigger_enabled)
        for w in self._workers:
            w.sig_set_upper_threshold.emit(val)

    @pyqtSlot(float)
    def _onTriggerLowerChanged(self, val: float) -> None:
        self._trigger_low = val
        self._waveform.set_thresholds(
            self._trigger_high, val, self._trigger_enabled)
        for w in self._workers:
            w.sig_set_lower_threshold.emit(val)

    @pyqtSlot(int)
    def _onTriggerDebounceChanged(self, samples: int) -> None:
        self._trigger_debounce = samples
        for w in self._workers:
            w.sig_set_debounce.emit(samples)

    # ── 阈值信号从画板来（双击/拖拽） ─────────────────

    @pyqtSlot(float)
    def _onUpperThresholdChanged(self, val: float) -> None:
        self._trigger_high = val
        # 更新面板控件值（不触发信号循环）
        self._trigger_panel.upper_spin.blockSignals(True)
        self._trigger_panel.upper_spin.setValue(val)
        self._trigger_panel.upper_spin.blockSignals(False)
        # 同步到 Worker
        for w in self._workers:
            w.sig_set_upper_threshold.emit(val)

    @pyqtSlot(float)
    def _onLowerThresholdChanged(self, val: float) -> None:
        self._trigger_low = val
        self._trigger_panel.lower_spin.blockSignals(True)
        self._trigger_panel.lower_spin.setValue(val)
        self._trigger_panel.lower_spin.blockSignals(False)
        for w in self._workers:
            w.sig_set_lower_threshold.emit(val)

    # ═══════════════════════════════════════════════════════
    # 序列化支持（供节点 serialize/deserialize 调用）
    # ═══════════════════════════════════════════════════════

    def get_state(self) -> dict:
        """获取 UI 状态用于序列化"""
        return {
            # 采集系统
            "fps": self._fps,
            "buffer_size": self._buffer_size,
            "sample_rate_hz": self._sample_rate_hz,
            # 水平系统
            "time_window": self._time_window_s,
            "scroll_offset": self._scrollbar.value(),
            # 垂直系统
            "y_range": self._y_range,
            "y_offset": self._y_offset,
            "line_width": self._line_width,
            # 触发系统
            "trigger_enabled": self._trigger_enabled,
            "trigger_mode": self._trigger_mode,
            "trigger_edge": self._trigger_edge,
            "trigger_high": self._trigger_high,
            "trigger_low": self._trigger_low,
            "trigger_debounce": self._trigger_debounce,
            # 通道
            "channels_visible": self._channel_visible,
            # 状态
            "started": self._started,
        }

    def set_state(self, data: dict) -> None:
        """从反序列化数据恢复 UI 状态"""
        # 采集系统
        self._fps = data.get("fps", 30)
        self._buffer_size = data.get("buffer_size", 1_000_000)
        self._sample_rate_hz = data.get("sample_rate_hz", 1000.0)
        self.fps_spin.setValue(self._fps)
        self.buffer_spin.setValue(self._buffer_size)
        self.sample_rate_spin.setValue(self._sample_rate_hz)

        # 水平系统
        self._time_window_s = data.get("time_window", 1.0)
        self.time_window_spin.setValue(self._time_window_s)
        scroll = data.get("scroll_offset", 0)
        self._scrollbar.setValue(scroll)

        # 垂直系统
        self._y_range = data.get("y_range", 10.0)
        self._y_offset = data.get("y_offset", 0.0)
        self._line_width = data.get("line_width", 2)
        self.y_range_spin.setValue(self._y_range)
        self.y_offset_spin.setValue(self._y_offset)
        self.line_width_spin.setValue(self._line_width)

        # 触发系统
        self._trigger_enabled = data.get("trigger_enabled", False)
        self._trigger_mode = data.get("trigger_mode", "auto")
        self._trigger_edge = data.get("trigger_edge", "rising")
        self._trigger_high = data.get("trigger_high", 1.0)
        self._trigger_low = data.get("trigger_low", -1.0)
        self._trigger_debounce = data.get("trigger_debounce", 5)
        self._trigger_panel.set_values(
            enabled=self._trigger_enabled,
            edge=self._trigger_edge,
            upper=self._trigger_high,
            lower=self._trigger_low,
            debounce=self._trigger_debounce,
            mode=self._trigger_mode)

        # 通道可见性
        vis = data.get("channels_visible", [True] * 4)
        for i in range(min(len(vis), 4)):
            self._channel_visible[i] = vis[i]
            if i < len(self._chk_boxes):
                self._chk_boxes[i].setChecked(vis[i])

        # 运行状态
        self._started = data.get("started", False)
        if self._started:
            self.start_btn.setChecked(True)
            # 如果之前是启动状态，自动启动 Worker
            for w in self._workers:
                w.start()

    # ═══════════════════════════════════════════════════════
    # 生命周期
    # ═══════════════════════════════════════════════════════

    def cleanup(self) -> None:
        """清理资源：停止所有 Worker、退出线程"""
        # 停止 Worker
        for w in self._workers:
            w.stop()
            w.deleteLater()

        # 退出线程
        for t in self._threads:
            t.quit()
            t.wait(3000)
            t.deleteLater()

        self._workers.clear()
        self._threads.clear()
