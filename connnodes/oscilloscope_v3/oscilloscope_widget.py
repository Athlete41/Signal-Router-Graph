"""
示波器 V3 — 内容部件 UI + 双线程管理

纯显示节点：接收数据写入RingA，渲染到WaveformView。
触发由独立的 trigger_v3 节点处理。
"""
from __future__ import annotations

from PyQt5.QtCore import (QMetaObject, QObject, Qt, QThread,
                          QTimer, pyqtSlot)

from conn_base import ConnNodeContentWidget
from conn_utils import ThreadManager

from .data_core import DataCore
from .oscilloscope_ui import Ui_OscilloscopeV3
from .render_core import RenderCore

_CONTROL_FLOW_DEBUG = False  # True=主线程调试模式(Qt线程代码无法命中断点)


# ── 工作线程 Worker ──────────────────────────────────

class _DataWorker(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.core: DataCore | None = None

    @pyqtSlot()
    def initCore(self) -> None:
        self.core = DataCore()


class _RenderWorker(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.core: RenderCore | None = None

    @pyqtSlot()
    def initCore(self) -> None:
        self.core = RenderCore()


# ── 内容部件 ─────────────────────────────────────────

class OscilloscopeV3Content(ConnNodeContentWidget):
    """示波器 V3 内容部件"""

    def __init__(self, node):
        super().__init__(node)
        self._data_worker: _DataWorker | None = None
        self._render_worker: _RenderWorker | None = None

    def initUI(self) -> None:
        self._create_workers()
        self.ui = Ui_OscilloscopeV3()
        self.ui.setupUi(self)
        self._wire_signals()

        # ── 默认渲染就绪（定时器已由 WV 内部管理）──
        self.ui.waveform_view.rebuild_overlay()

        self.setStyleSheet(self._style_sheet())
        self.setNodeSize(800, 760)

        # ── 注入 interval 读取回调 + 启动 WV 内部定时器 ──
        wv = self.ui.waveform_view
        wv.set_interval_source(lambda: self._interval_us[0])
        wv.set_fps(self.ui.fps_spin.value())


    def _create_workers(self) -> None:
        """创建工作线程并初始化"""
        if _CONTROL_FLOW_DEBUG:
            # 调试模式：数据/渲染对象在主线程创建，方便断点调试
            self._data_worker = None
            self._render_worker = None
            self._data_thread = None
            self._render_thread = None
            self._dc = DataCore()
            self._rc = RenderCore()
            self._rc.ring_a_ref = self._dc.ring_a
        else:
            # ── 数据决策线程 ──
            self._data_worker = _DataWorker()
            self._data_thread = QThread()
            self._data_thread.start()
            ThreadManager.instance().register_thread(self._data_thread)
            self._data_worker.moveToThread(self._data_thread)
            QMetaObject.invokeMethod(self._data_worker, "initCore",
                                     Qt.BlockingQueuedConnection)
            self._dc = self._data_worker.core  # type: DataCore

            # ── 渲染帧线程 ──
            self._render_worker = _RenderWorker()
            self._render_thread = QThread()
            self._render_thread.start()
            ThreadManager.instance().register_thread(self._render_thread)
            self._render_worker.moveToThread(self._render_thread)
            QMetaObject.invokeMethod(self._render_worker, "initCore",
                                     Qt.BlockingQueuedConnection)
            self._rc = self._render_worker.core  # type: RenderCore

            # ── 共享 RingA 引用（RenderCore 读 data 用）──
            self._rc.ring_a_ref = self._dc.ring_a

        # ── 共享 interval_us 容器（DataCore 直接写入，Content 定时器读取）──
        self._interval_us = [0]
        self._dc.interval_us_ref = self._interval_us

    def _wire_signals(self) -> None:
        """跨线程信号接线"""
        dc = self._dc
        rc = self._rc
        wv = self.ui.waveform_view
        ui = self.ui

        # 注入 RC 的 WV 引用（RC 写入 pending_path）
        rc._waveform_view = wv

        # 注入心跳控件
        wv.set_heartbeat(ui.heartbeat)

        # 绑定滚动条
        wv.set_scrollbar(ui.x_scroll_bar)

        # WV → RC：渲染请求（QueuedConnection 跨线程）
        wv.render_request.connect(rc.on_render_request, Qt.QueuedConnection)

        # RC → WV：渲染完成（WV 内部管理背压）
        rc.waveform_ready.connect(wv.on_render_path)

        # ── Overlay 更新定时器（1 Hz，不随渲染帧率走）──
        self._overlay_timer = QTimer(self)
        self._overlay_timer.timeout.connect(self._on_overlay_update)
        self._overlay_timer.start(1000)

        # ── UI → WV（编辑 spinbox 修改参数）──
        ui.x_window_ms_spin.valueChanged.connect(wv.set_x_window_ms)
        ui.y_window_mv_1_spin.valueChanged.connect(wv.set_y_window_mv_1)
        ui.y_offset_mv_1_spin.valueChanged.connect(wv.set_y_offset_mv_1)
        ui.y_window_mv_2_spin.valueChanged.connect(wv.set_y_window_mv_2)
        ui.y_offset_mv_2_spin.valueChanged.connect(wv.set_y_offset_mv_2)

        # ── WV → UI（鼠标交互修改参数后同步到 spinbox）──
        wv.x_window_changed.connect(self._on_x_window_changed)
        wv.y_window_mv_1_changed.connect(self._on_y_window_mv_1_changed)
        wv.y_offset_mv_1_changed.connect(self._on_y_offset_mv_1_changed)
        wv.y_window_mv_2_changed.connect(self._on_y_window_mv_2_changed)
        wv.y_offset_mv_2_changed.connect(self._on_y_offset_mv_2_changed)

        # 网格格数
        ui.x_div_spin.valueChanged.connect(self._on_x_div_changed)
        ui.y_div_spin.valueChanged.connect(self._on_y_div_changed)

        # 帧率（直接控制 WV 内部定时器）
        ui.fps_spin.valueChanged.connect(wv.set_fps)

        # 存储深度
        ui.memory_depth_spin.valueChanged.connect(self._on_mem_depth_changed)

        # 抗锯齿
        ui.aa_check.toggled.connect(wv.set_antialiasing)

        # 刻度绘制
        ui.show_scale_check.toggled.connect(wv.set_show_scale)

        # ── 工具栏按钮 ──
        ui.stop_btn.toggled.connect(self._on_stop_toggled)
        ui.clear_btn.clicked.connect(self._on_clear)
        ui.save_btn.clicked.connect(self._on_save)
        ui.ch_select_btn.toggled.connect(self._on_ch_select_toggled)

    @staticmethod
    def _style_sheet() -> str:
        return """
            QLabel {
                color: #f0f0f0;
                background-color: transparent;
            }
            QGroupBox {
                color: #f0f0f0;
                border: 1px solid #555;
                border-radius: 4px;
                margin-top: 8px;
                font-weight: bold;
            }
            QGroupBox::title {
                color: #f0f0f0;
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
            QScrollBar:horizontal {
                background: #1e1e1e;
                height: 14px;
                border: none;
            }
            QScrollBar::handle:horizontal {
                background: #777;
                min-width: 30px;
                border-radius: 6px;
                margin: 2px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #999;
            }
            QScrollBar::handle:horizontal:pressed {
                background: #bbb;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """

    # ── 格式辅助 ────────────────────────────────────

    @staticmethod
    def _fmt_time(us: float) -> str:
        """微秒 → 自动选单位的字符串"""
        if us < 1:
            return f"{us * 1000:.1f} ns"
        elif us < 1000:
            return f"{us:.1f} µs"
        elif us < 1_000_000:
            return f"{us / 1000:.3f} ms"
        else:
            return f"{us / 1_000_000:.3f} s"

    @staticmethod
    def _fmt_voltage(mv: float) -> str:
        """毫伏 → 自动选单位的字符串（含 格）"""
        if mv < 1000:
            return f"{mv:.1f} mV/格"
        else:
            return f"{mv / 1000:.3f} V/格"

    # ── WaveformView → UI 同步（blockSignals 防环回）─

    def _on_x_window_changed(self, v: float) -> None:
        self.ui.x_window_ms_spin.blockSignals(True)
        self.ui.x_window_ms_spin.setValue(v)
        self.ui.x_window_ms_spin.blockSignals(False)

    def _on_y_window_mv_1_changed(self, v: float) -> None:
        self.ui.y_window_mv_1_spin.blockSignals(True)
        self.ui.y_window_mv_1_spin.setValue(v)
        self.ui.y_window_mv_1_spin.blockSignals(False)

    def _on_y_offset_mv_1_changed(self, v: float) -> None:
        self.ui.y_offset_mv_1_spin.blockSignals(True)
        self.ui.y_offset_mv_1_spin.setValue(v)
        self.ui.y_offset_mv_1_spin.blockSignals(False)

    def _on_y_window_mv_2_changed(self, v: float) -> None:
        self.ui.y_window_mv_2_spin.blockSignals(True)
        self.ui.y_window_mv_2_spin.setValue(v)
        self.ui.y_window_mv_2_spin.blockSignals(False)

    def _on_y_offset_mv_2_changed(self, v: float) -> None:
        self.ui.y_offset_mv_2_spin.blockSignals(True)
        self.ui.y_offset_mv_2_spin.setValue(v)
        self.ui.y_offset_mv_2_spin.blockSignals(False)

    # ── UI 控件 → 参数同步 ──────────────────────────

    @pyqtSlot(int)
    def _on_mem_depth_changed(self, depth: int) -> None:
        self._dc.set_mem_depth(depth)

    # ── 通道选择 ────────────────────────────────────

    @pyqtSlot(bool)
    def _on_ch_select_toggled(self, checked: bool) -> None:
        """切换激活通道 1/2"""
        ch = 2 if checked else 1
        self.ui.waveform_view.set_active_channel(ch)
        color = "#00FFFF" if checked else "#FFFF00"
        text = "CH2" if checked else "CH1"
        self.ui.ch_select_btn.setStyleSheet(f"color: {color};")
        self.ui.ch_select_btn.setText(text)

    # ── 工具栏按钮 ──────────────────────────────────

    @pyqtSlot(bool)
    def _on_stop_toggled(self, checked: bool) -> None:
        """停止按钮：仅控制 DataCore 是否接受新数据（图标由 QIcon.On/Off 自动切换）"""
        self._dc.set_accept_data(not checked)
        self.ui.stop_btn.setText("停止" if checked else "启动")

    @pyqtSlot()
    def _on_clear(self) -> None:
        """清理按钮：清空存储器 + 清波形路径，保留网格和信息"""
        self._dc.clear_data()
        self.ui.waveform_view.clear_waveforms()

    @pyqtSlot()
    def _on_save(self) -> None:
        """保存按钮：将通道数据导出为 JSON"""
        from PyQt5.QtWidgets import QFileDialog
        import json
        path, _ = QFileDialog.getSaveFileName(
            self, "保存波形数据", "", "JSON (*.json)")
        if not path:
            return
        data = self._dc.export_data()
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    # ── 信息标签更新（1 Hz 定时器）────────────────────

    @pyqtSlot()
    def _on_overlay_update(self) -> None:
        """定时器到期 → 刷新各信息 QLabel"""
        wv = self.ui.waveform_view
        v_div = self.ui.y_div_spin.value()
        interval_us = self._interval_us[0]

        ch1_pts = len(self._dc.ring_a["1"])
        ch2_pts = len(self._dc.ring_a["2"])

        v1_mv = wv.get_y_window_mv_1() / v_div
        ch1_dur_ms = ch1_pts * interval_us / 1000

        v2_mv = wv.get_y_window_mv_2() / v_div
        ch2_dur_ms = ch2_pts * interval_us / 1000

        # 水平系统信息标签
        self.ui.sampling_interval_label.setText(f"{interval_us:.1f} µs")
        self.ui.input1_pts_dur_label.setText(f"{ch1_pts:,} 点, {ch1_dur_ms:.3f} ms")
        self.ui.input2_pts_dur_label.setText(f"{ch2_pts:,} 点, {ch2_dur_ms:.3f} ms")

        # input 组 div 标签
        self.ui.ch1_div_label.setText(self._fmt_voltage(v1_mv))
        self.ui.ch2_div_label.setText(self._fmt_voltage(v2_mv))

    @pyqtSlot(float)
    def _on_x_div_changed(self, div: float) -> None:
        self.ui.waveform_view.set_grid_div(h_div=div)

    @pyqtSlot(float)
    def _on_y_div_changed(self, div: float) -> None:
        self.ui.waveform_view.set_grid_div(v_div=div)

    # ── 析构清理 ──────────────────────────────────────

    def cleanup(self) -> None:
        self._overlay_timer.stop()

        if not _CONTROL_FLOW_DEBUG:
            workers = [
                (self._data_worker, self._data_thread),
                (self._render_worker, self._render_thread),
            ]
            for worker, thread in workers:
                if worker:
                    worker.deleteLater()
                if thread:
                    thread.quit()
                    thread.wait(3000)
                    thread.deleteLater()

        self._data_worker = None
        self._render_worker = None
        self._data_thread = None
        self._render_thread = None
        self._interval_us = None
        self._dc = None
        self._rc = None

        self.ui.waveform_view.cleanup()
        self.ui = None
