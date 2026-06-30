"""
波形显示组件 — WaveformView

网格线 + 双缓冲波形绘制。
双缓冲：RenderCore 写 pending_path_1/2，on_render_path 交换到 path_1/2，paintEvent 绘制。

paintEvent 覆盖方案（方案 C）：
  super().paintEvent() 画 scene 项（网格/信息），再 QPainter.drawPath() 画波形。
"""
from __future__ import annotations

import time

from PyQt5.QtCore import Qt, QRectF, QTimer, pyqtSignal
from PyQt5.QtGui import (QBrush, QColor, QPainter, QPen)
from PyQt5.QtWidgets import (QGraphicsLineItem, QGraphicsScene,
    QGraphicsView, QWidget, QScrollBar, QSizePolicy)
from PyQt5.QtGui import QPainterPath

from .heartbeat import HeartbeatWidget


class WaveformView(QGraphicsView):
    """波形显示视图（双缓冲 + paintEvent 绘制波形）"""

    render_request = pyqtSignal(object)  # params: dict → RenderCore.on_render_request

    # ── 参数变化信号（UI 同步用）──
    x_window_changed = pyqtSignal(float)
    y_window_mv_1_changed = pyqtSignal(float)
    y_offset_mv_1_changed = pyqtSignal(float)
    y_window_mv_2_changed = pyqtSignal(float)
    y_offset_mv_2_changed = pyqtSignal(float)

    # ── 双缓冲 QPainterPath ──
    # 注意：这些是类级别类型标注，实例属性在 __init__ 中初始化
    # 不要在这里赋值（会导致类属性而非实例属性）

    # 默认初始尺寸
    _DEFAULT_WIDTH = 600
    _DEFAULT_HEIGHT = 300

    # 色系
    COLOR_GRID = QColor("#555555")
    COLOR_1 = QColor("#FFFF00")
    COLOR_2 = QColor("#00FFFF")
    COLOR_ZERO = QColor("#00FF00")
    COLOR_BG = QColor("#1A1A1A")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # ── 双缓冲 QPainterPath ──
        self.path_1: QPainterPath | None = None          # active，paintEvent 读
        self.path_2: QPainterPath | None = None
        self.pending_path_1: QPainterPath | None = None  # pending，RenderCore 写
        self.pending_path_2: QPainterPath | None = None

        # ── 动态尺寸 ──
        self._view_w = self._DEFAULT_WIDTH
        self._view_h = self._DEFAULT_HEIGHT

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._scene.setSceneRect(0, 0, self._view_w, self._view_h)

        self.setRenderHint(QPainter.Antialiasing, True)
        self._antialiasing = True
        self.setRenderHint(QPainter.SmoothPixmapTransform, False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setInteractive(False)
        self.setViewportUpdateMode(QGraphicsView.MinimalViewportUpdate)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(200, 100)
        self.setBackgroundBrush(QBrush(self.COLOR_BG))

        # ── 网格格数（可通过 set_grid_div 调整）──
        self._grid_h_div = 10
        self._grid_v_div = 8

        # ── x_scroll 状态 ──
        self._x_scroll: int | None = None  # None=自动滚动，int=手动定位

        # ── 滚轮事件开关（ConnDMGraphicsView 读取）──
        self.enableWheelEvent = True

        # ── 滚动条（外部传入，由 WV 管理值同步）──
        self._hbar: QScrollBar | None = None

        # ── 参数存储（由外部更新）──
        self._x_window_ms: float = 1000.0
        self._y_window_mv_1: float = 2000.0
        self._y_offset_mv_1: float = 0.0
        self._y_window_mv_2: float = 2000.0
        self._y_offset_mv_2: float = 0.0
        self._interval_us: int = 0
        self._total_pts: int = 0
        self._window_pt: int = 0

        # ── 通道选择（1=CH1, 2=CH2）──
        self._active_channel: int = 1

        # ── 鼠标拖拽状态 ──
        self._drag_mode: str | None = None  # None / "h_scroll" / "offset"
        self._drag_start_x: int = 0
        self._drag_start_y: int = 0
        self._drag_start_x_scroll: int = 0

        # ── 内部刷新定时器（取代 Content 的定时器）──
        self._render_busy: bool = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._on_refresh_tick)
        self._interval_source: callable | None = None
        self._fps: int = 30

        # ── 心跳检测 ──
        self._heartbeat: HeartbeatWidget | None = None
        self._last_beat_count: int = -1
        self._heartbeat_stopped: bool = False
        self._heartbeat_stop_time: float = 0.0

        # ── 刻度绘制开关 ──
        self._show_scale: bool = True

        # ── 图形项 ──
        self._grid_items: list[QGraphicsLineItem] = []

        # ── 预创建静态画笔 ──
        self._pen_1 = QPen(self.COLOR_1, 1.2)
        self._pen_2 = QPen(self.COLOR_2, 1.2)
        self._pen_zero = QPen(self.COLOR_ZERO, 1, Qt.DashLine)

        self._build_grid()

    # ── 参数更新入口（UI / 鼠标交互调用，值变时发射信号）──

    def set_x_window_ms(self, ms: float) -> None:
        if self._x_window_ms != ms:
            self._x_window_ms = ms
            self.x_window_changed.emit(ms)

    def set_y_window_mv_1(self, mv: float) -> None:
        if self._y_window_mv_1 != mv:
            self._y_window_mv_1 = mv
            self.y_window_mv_1_changed.emit(mv)

    def set_y_window_mv_2(self, mv: float) -> None:
        if self._y_window_mv_2 != mv:
            self._y_window_mv_2 = mv
            self.y_window_mv_2_changed.emit(mv)

    def set_y_offset_mv_1(self, mv: float) -> None:
        if self._y_offset_mv_1 != mv:
            self._y_offset_mv_1 = mv
            self.y_offset_mv_1_changed.emit(mv)

    def set_y_offset_mv_2(self, mv: float) -> None:
        if self._y_offset_mv_2 != mv:
            self._y_offset_mv_2 = mv
            self.y_offset_mv_2_changed.emit(mv)

    # ── getter（UI / serialize 读值用）──

    def get_x_window_ms(self) -> float:
        return self._x_window_ms

    def get_y_window_mv_1(self) -> float:
        return self._y_window_mv_1

    def get_y_offset_mv_1(self) -> float:
        return self._y_offset_mv_1

    def get_y_window_mv_2(self) -> float:
        return self._y_window_mv_2

    def get_y_offset_mv_2(self) -> float:
        return self._y_offset_mv_2

    def set_interval_us(self, us: int) -> None:
        self._interval_us = us

    def set_grid_div(self, h_div: float | None = None,
                     v_div: float | None = None) -> None:
        """调整网格格数并重建"""
        if h_div is not None:
            self._grid_h_div = max(1, int(h_div))
        if v_div is not None:
            self._grid_v_div = max(1, int(v_div))
        self._rebuild_grid()

    # ── 抗锯齿开关 ─────────────────────────────

    def set_antialiasing(self, enabled: bool) -> None:
        """开关抗锯齿渲染"""
        self._antialiasing = enabled
        self.setRenderHint(QPainter.Antialiasing, enabled)
        self.viewport().update()

    # ── 滚动条绑定 ──────────────────────────────

    def set_scrollbar(self, bar: QScrollBar) -> None:
        """绑定外部水平滚动条"""
        self._hbar = bar
        bar.setRange(0, 0)  # 无数据时滑块不显示指向位置
        bar.valueChanged.connect(self._on_scrollbar_dragged)

    def _on_scrollbar_dragged(self, value: int) -> None:
        """用户拖滚动条 → 切到手动模式"""
        self._x_scroll = value

    # ── 渲染请求 ────────────────────────────────

    def request_render(self) -> None:
        """定时器触发 → 收集当前参数 → 发给 RenderCore"""
        params = {
            "x_window_ms":    self._x_window_ms,
            "x_scroll":       self._x_scroll,
            "y_window_mv_1":  self._y_window_mv_1,
            "y_offset_mv_1":  self._y_offset_mv_1,
            "y_window_mv_2":  self._y_window_mv_2,
            "y_offset_mv_2":  self._y_offset_mv_2,
            "screen_w":       self._view_w,
            "screen_h":       self._view_h,
            "interval_us":    self._interval_us,
        }
        self.render_request.emit(params)

    # ── 渲染响应 ────────────────────────────────

    def on_render_path(self, start: int, total_pts: int, window_pt: int) -> None:
        """收到 waveform_ready → 交换双缓冲 + 滚动条同步 + 自动回 None + 触发重绘"""
        self._total_pts = total_pts
        self._window_pt = window_pt

        # 交换双缓冲：pending → active，旧 active 丢弃
        self.path_1, self.pending_path_1 = self.pending_path_1, self.path_1
        self.path_2, self.pending_path_2 = self.pending_path_2, self.path_2

        # 处理滑动条相关
        if self._hbar is not None:
            self._hbar.blockSignals(True)
            self._hbar.setRange(0, max(0, total_pts - window_pt))
            self._hbar.setValue(start)
            self._hbar.blockSignals(False)

        # 自动回 None：窗口已到最新数据尾部
        if self._drag_mode is None and self._x_scroll is not None and start >= total_pts - window_pt:
            self._x_scroll = None

        # 渲染完成：重置 RenderCore 背压标志
        self._render_busy = False
        # self.viewport().update()

    # ── 大小变化 ──────────────────────────────────

    def resizeEvent(self, event) -> None:
        """视图大小变化时重建场景，同步心跳尺寸"""
        super().resizeEvent(event)
        w = self.width()
        h = self.height()
        if w == self._view_w and h == self._view_h:
            return
        self._view_w = w
        self._view_h = h
        self._scene.setSceneRect(0, 0, w, h)
        self._rebuild_grid()
        # 同步心跳尺寸
        if self._heartbeat is not None:
            self._heartbeat.setGeometry(0, 0, w, h)

    def get_view_width(self) -> int:
        return self._view_w

    def get_view_height(self) -> int:
        return self._view_h

    # ── paintEvent 覆盖（方案 C） ───────────────

    def paintEvent(self, event) -> None:
        """先画 scene（网格/文字），再画波形"""
        super().paintEvent(event)  # 画 scene 已有项（grid + info）

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing, self._antialiasing)

        if self.path_1 is not None:
            painter.setPen(self._pen_1)
            painter.drawPath(self.path_1)

        if self.path_2 is not None:
            painter.setPen(self._pen_2)
            painter.drawPath(self.path_2)

        # ── 刻度绘制（可选）──
        if self._show_scale:
            self._draw_scale_marks(painter)

        painter.end()

    # ── 刻度绘制（可选）────────────────────────────

    @staticmethod
    def _fmt_time_by_window(ms: float, window_ms: float) -> str:
        """根据时间窗口统一单位格式化时间值"""
        if window_ms >= 1000:
            return f"{ms/1000:.2f}s"
        elif window_ms >= 1:
            return f"{ms:.2f}ms"
        else:
            return f"{ms*1000:.0f}µs"

    @staticmethod
    def _fmt_voltage_by_range(mv: float, range_mv: float) -> str:
        """根据电压范围统一单位格式化电压值"""
        if range_mv >= 1000:
            return f"{mv/1000:.3f}V"
        else:
            return f"{mv:.1f}mV"

    def _draw_scale_marks(self, painter: QPainter) -> None:
        """在波形之上绘制水平时间 + 垂直电压刻度"""
        w, h = self._view_w, self._view_h
        if w <= 0 or h <= 0:
            return

        # ── 水平刻度（底部，灰色，边界保护）──
        h_step = w / self._grid_h_div
        time_per_div = self._x_window_ms / self._grid_h_div
        RECT_W = 60

        painter.setPen(QColor("#C0C0C0"))
        painter.setFont(self.font())
        for i in range(self._grid_h_div + 1):
            x = i * h_step
            t_ms = i * time_per_div
            label = self._fmt_time_by_window(t_ms, self._x_window_ms)
            # 边界保护：clamp rx 使 rect 不超出左右边缘
            rx = max(0, min(w - RECT_W, x - RECT_W / 2))
            painter.drawText(QRectF(rx, h - 14, RECT_W, 12),
                             Qt.AlignCenter, label)

        # ── 垂直刻度（中心线右侧，CH1 黄 在上 / CH2 青 在下）──
        v_step = h / self._grid_v_div
        cy = h / 2.0
        TEXT_W = 80
        LINE_H = 12
        vx = w // 2 + 10  # 中心线右侧

        y_win_1 = self._y_window_mv_1
        y_win_2 = self._y_window_mv_2
        y_off_1 = self._y_offset_mv_1
        y_off_2 = self._y_offset_mv_2

        for i in range(self._grid_v_div + 1):
            y = i * v_step

            # 电压换算：逆映射 RenderCore._y()
            if y_win_1 > 0 and cy > 0:
                ch1_mv = y_off_1 + (cy - y) / cy * y_win_1 / 2
            else:
                ch1_mv = 0.0
            if y_win_2 > 0 and cy > 0:
                ch2_mv = y_off_2 + (cy - y) / cy * y_win_2 / 2
            else:
                ch2_mv = 0.0

            label1 = self._fmt_voltage_by_range(ch1_mv, y_win_1)
            label2 = self._fmt_voltage_by_range(ch2_mv, y_win_2)

            # CH1 黄色 — 格线上方；CH2 青色 — 格线下方
            t1y = y - LINE_H
            t2y = y + 1

            # 边界保护：整体偏移，保持间距不重叠
            if t1y < 0:
                delta = -t1y
                t1y = 0
                t2y += delta
            elif t2y + LINE_H > h:
                delta = t2y + LINE_H - h
                t1y -= delta
                t2y = h - LINE_H

            painter.setPen(self.COLOR_1)
            painter.drawText(QRectF(vx, t1y, TEXT_W, LINE_H),
                             Qt.AlignCenter, label1)
            painter.setPen(self.COLOR_2)
            painter.drawText(QRectF(vx, t2y, TEXT_W, LINE_H),
                             Qt.AlignCenter, label2)

    # ── 网格构建 ──────────────────────────────────

    def _clear_grid(self) -> None:
        for item in self._grid_items:
            self._scene.removeItem(item)
        self._grid_items.clear()

    def _build_grid(self) -> None:
        """创建网格线"""
        w, h = self._view_w, self._view_h
        h_step = w / self._grid_h_div
        v_step = h / self._grid_v_div
        pen = QPen(self.COLOR_GRID, 1)

        # 水平线
        for i in range(self._grid_v_div + 1):
            y = i * v_step
            line = QGraphicsLineItem(0, y, w, y)
            line.setPen(pen)
            self._scene.addItem(line)
            self._grid_items.append(line)

        # 垂直线
        for i in range(self._grid_h_div + 1):
            x = i * h_step
            line = QGraphicsLineItem(x, 0, x, h)
            line.setPen(pen)
            self._scene.addItem(line)
            self._grid_items.append(line)

        # 中心十字线（绿色虚线高亮）
        cx, cy = w / 2, h / 2
        center_pen = QPen(self.COLOR_ZERO, 1, Qt.DashLine)
        cx_line = QGraphicsLineItem(cx, 0, cx, h)
        cx_line.setPen(center_pen)
        self._scene.addItem(cx_line)
        self._grid_items.append(cx_line)

        cy_line = QGraphicsLineItem(0, cy, w, cy)
        cy_line.setPen(center_pen)
        self._scene.addItem(cy_line)
        self._grid_items.append(cy_line)

    def _rebuild_grid(self) -> None:
        """尺寸变化时重建网格"""
        self._clear_grid()
        self._build_grid()

    # ── 重建场景 ──────────────────────────────────

    def rebuild_overlay(self) -> None:
        """重建网格（启动时调用）"""
        self._build_grid()
        self.viewport().update()

    def clear_all(self) -> None:
        """清除网格和波形（停止时调用），画面完全空白"""
        self._clear_grid()
        self.path_1 = None
        self.path_2 = None
        self.pending_path_1 = None
        self.pending_path_2 = None
        self._x_scroll = None
        self._total_pts = 0
        self._window_pt = 0
        if self._hbar is not None:
            self._hbar.blockSignals(True)
            self._hbar.setRange(0, 0)
            self._hbar.setValue(0)
            self._hbar.blockSignals(False)
        self.viewport().update()

    def clear_waveforms(self) -> None:
        """仅清波形路径 + 重置滚动条，保留网格和叠加信息"""
        self.path_1 = None
        self.path_2 = None
        self.pending_path_1 = None
        self.pending_path_2 = None
        self._x_scroll = None
        self._total_pts = 0
        self._window_pt = 0
        if self._hbar is not None:
            self._hbar.blockSignals(True)
            self._hbar.setRange(0, 0)
            self._hbar.setValue(0)
            self._hbar.blockSignals(False)
        self.viewport().update()

    def reset_scroll(self) -> None:
        """重置水平滚动切回自动"""
        self._x_scroll = None

    # ── 刷新定时器管理 ────────────────────────────

    def set_interval_source(self, source: callable | None) -> None:
        """设置 interval_us 读取回调（由 Content 注入）"""
        self._interval_source = source

    def set_fps(self, fps: int) -> None:
        """帧率变化 → 重启内部定时器"""
        self._fps = fps
        self._refresh_timer.start(int(1000 / fps))

    # ── 心跳检测 ────────────────────────────────────

    def set_heartbeat(self, hb: HeartbeatWidget | None) -> None:
        """注入 HeartbeatWidget，铺满 viewport 监测 paintEvent"""
        self._heartbeat = hb
        if hb is not None:
            hb.setParent(self.viewport())
            hb.setGeometry(0, 0, self._view_w, self._view_h)

    def set_show_scale(self, enabled: bool) -> None:
        """开关刻度绘制（由 UI 复选框控制）"""
        if self._show_scale != enabled:
            self._show_scale = enabled
            self.viewport().update()

    _HEARTBEAT_TIMEOUT = 1.5  # 心跳停止超过此秒数则跳过渲染

    def _on_refresh_tick(self) -> None:
        """内部定时器到期：心跳检测 → 背压保护 → 读 interval → 触发渲染"""
        # 1. 心跳检测
        hb = self._heartbeat
        if hb is not None:
            if hb.beat_count != self._last_beat_count:
                self._last_beat_count = hb.beat_count
                self._heartbeat_stopped = False
            else:
                if not self._heartbeat_stopped:
                    self._heartbeat_stop_time = time.monotonic()
                    self._heartbeat_stopped = True
                elif time.monotonic() - self._heartbeat_stop_time > self._HEARTBEAT_TIMEOUT:
                    return  # 心跳停止超过阈值，跳过渲染

        # 2. RenderCore 背压保护
        if self._render_busy:
            return

        # 3. 读 interval 并请求渲染
        if self._interval_source is not None:
            self._interval_us = self._interval_source()
        self.request_render()

    # ── 鼠标交互 ──────────────────────────────────

    def wheelEvent(self, event) -> None:
        """滚轮缩放时间窗口 / Shift+滚轮缩放范围"""
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.2 ** (-delta / 120)  # 上滚缩小(zoom in)，下滚放大(zoom out)

        if event.modifiers() & Qt.ShiftModifier:
            # Shift+滚轮：缩放所选通道的垂直范围
            if self._active_channel == 1:
                new_mv = self._y_window_mv_1 * factor
                new_mv = max(0.1, min(100_000.0, new_mv))
                self.set_y_window_mv_1(new_mv)
            else:
                new_mv = self._y_window_mv_2 * factor
                new_mv = max(0.1, min(100_000.0, new_mv))
                self.set_y_window_mv_2(new_mv)
        else:
            # 滚轮：缩放时间窗口
            new_ms = self._x_window_ms * factor
            new_ms = max(0.001, min(100_000.0, new_ms))
            self.set_x_window_ms(new_ms)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start_x = event.x()
            self._drag_start_y = event.y()
            if event.modifiers() & Qt.ShiftModifier:
                # Shift+左键：调偏移
                self._drag_mode = "offset"
                self._drag_start_offset = (
                    self._y_offset_mv_1 if self._active_channel == 1
                    else self._y_offset_mv_2
                )
            else:
                # 左键：水平滚动
                self._drag_mode = "h_scroll"
                # auto-scroll 时取当前末端位置，避免跳 0
                if self._x_scroll is None:
                    self._drag_start_x_scroll = max(0, self._total_pts - self._window_pt)
                else:
                    self._drag_start_x_scroll = self._x_scroll
            self.setCursor(Qt.ClosedHandCursor)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        mode = self._drag_mode
        if mode is None:
            super().mouseMoveEvent(event)
            return

        dx = event.x() - self._drag_start_x
        dy = event.y() - self._drag_start_y

        if mode == "h_scroll":
            total_range = self._total_pts - self._window_pt
            if total_range > 0 and self._view_w > 0:
                x_delta = round(-dx * self._window_pt / self._view_w)
                new_x = self._drag_start_x_scroll + x_delta
                new_x = max(0, min(total_range, new_x))
                if self._x_scroll is None or self._x_scroll != new_x:
                    self._x_scroll = new_x
                    if self._hbar is not None:
                        self._hbar.blockSignals(True)
                        self._hbar.setValue(new_x)
                        self._hbar.blockSignals(False)

        elif mode == "offset":
            # Shift+拖拽：调偏移，灵敏度 = 窗口范围 / 视图高度
            if self._view_h > 0:
                if self._active_channel == 1:
                    range_mv = self._y_window_mv_1
                    delta_mv = -dy * range_mv / self._view_h
                    new_offset = self._drag_start_offset + delta_mv
                    new_offset = max(-100_000, min(100_000, new_offset))
                    self.set_y_offset_mv_1(new_offset)
                else:
                    range_mv = self._y_window_mv_2
                    delta_mv = -dy * range_mv / self._view_h
                    new_offset = self._drag_start_offset + delta_mv
                    new_offset = max(-100_000, min(100_000, new_offset))
                    self.set_y_offset_mv_2(new_offset)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_mode is not None:
            self._drag_mode = None
            self.unsetCursor()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """双击切回自动滚动"""
        self._x_scroll = None
        super().mouseDoubleClickEvent(event)

    # ── 通道选择 ──────────────────────────────────

    def set_active_channel(self, ch: int) -> None:
        """设置激活通道（1=CH1, 2=CH2）"""
        self._active_channel = ch

    # ── cleanup ──────────────────────────────────

    def cleanup(self) -> None:
        self._refresh_timer.stop()
        self._scene.clear()
        self._grid_items.clear()
        self.path_1 = None
        self.path_2 = None
        self.pending_path_1 = None
        self.pending_path_2 = None
        self._hbar = None
