"""
示波器 V3 — WaveformWidget（波形画板）

纯绘制组件，不缓存任何通道数据。
每次 paintEvent 通过 _content.iter_draw_channels() 获取 Worker 的
共享包络变量，实时读取后绘制。

绘制流程:
    1. 网格缓存 QPixmap（resize/Y 变化时重建）
    2. 遍历通道 → 读取 worker._envelope_vmin/vmax
    3. 可见窗口截取 → 坐标映射 → drawLines() 批量绘制
    4. 阈值线绘制（本地缓存）
"""

from __future__ import annotations

import numpy as np
from PyQt5.QtCore import (QLineF, QPointF, Qt, QTimer, pyqtSignal)
from PyQt5.QtGui import (QColor, QPainter, QPen, QPixmap)
from PyQt5.QtWidgets import QWidget


# ── 预定义通道颜色（8 色循环） ────────────────────────────
CHANNEL_COLORS = [
    QColor(0, 255, 0),      # 绿
    QColor(255, 255, 0),    # 黄
    QColor(0, 255, 255),    # 青
    QColor(255, 0, 255),    # 品红
    QColor(255, 165, 0),    # 橙
    QColor(160, 32, 240),   # 紫
    QColor(100, 149, 237),  # 蓝
    QColor(255, 192, 203),  # 粉
]


class WaveformWidget(QWidget):
    """波形画板

    信号:
        sig_upper_threshold_changed(float): 上阈值变更（双击/拖拽）
        sig_lower_threshold_changed(float): 下阈值变更
        sig_threshold_drag_started(): 拖拽开始
        sig_threshold_drag_finished(): 拖拽结束
    """

    sig_upper_threshold_changed = pyqtSignal(float)
    sig_lower_threshold_changed = pyqtSignal(float)
    sig_threshold_drag_started = pyqtSignal()
    sig_threshold_drag_finished = pyqtSignal()

    def __init__(self, content, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(200, 150)
        self.setMouseTracking(True)

        # -- 反向引用（非数据缓存） --
        self._content = content

        # -- 绘制参数 --
        self._y_range = 10.0          # Y 范围（峰峰值）
        self._y_offset = 0.0          # Y 偏移
        self._line_width = 2          # 波形线宽
        self._margin = (60, 20, 20, 20)  # 左、上、右、下
        self._screen_w = 800          # 屏幕宽度

        # -- 渲染优化 --
        self._grid_cache: QPixmap | None = None

        # -- 主动绘制定时器 --
        self._paint_timer = QTimer(self)
        self._paint_timer.timeout.connect(self.update)
        self._paint_timer.start(33)   # ~30 FPS

        # -- 阈值缓存（本地，权威值在 Worker） --
        self._upper_thresh = 1.0
        self._lower_thresh = -1.0
        self._show_thresholds = False

        # -- 拖拽状态 --
        self._drag_target = None       # "upper" / "lower" / None
        self._drag_start_y = 0
        self._drag_start_value = 0.0

    # ═══════════════════════════════════════════════════════
    # 绘制参数（由 Content 设置）
    # ═══════════════════════════════════════════════════════

    def set_y_range(self, r: float) -> None:
        self._y_range = max(r, 0.1)
        self._grid_cache = None   # 网格失效
        self.update()

    def set_y_offset(self, offset: float) -> None:
        self._y_offset = offset
        self._grid_cache = None
        self.update()

    def set_line_width(self, w: int) -> None:
        self._line_width = max(w, 1)
        self.update()

    def set_fps(self, fps: int) -> None:
        interval = max(int(1000 / fps), 16)  # 下限 ~60FPS
        self._paint_timer.setInterval(interval)

    def set_thresholds(self, upper: float, lower: float,
                       show: bool = True) -> None:
        """设置阈值绘制值（由 Content 在反序列化或 Worker 返回时调用）"""
        self._upper_thresh = upper
        self._lower_thresh = lower
        self._show_thresholds = show
        self.update()

    # ═══════════════════════════════════════════════════════
    # 事件
    # ═══════════════════════════════════════════════════════

    def resizeEvent(self, event) -> None:
        self._grid_cache = None
        self._screen_w = self.width()
        # 通知所有 Worker 屏幕宽变更
        for worker, _, _ in self._content.iter_draw_channels():
            worker.sig_set_screen_w.emit(self._screen_w)
        super().resizeEvent(event)

    # ═══════════════════════════════════════════════════════
    # 绘制
    # ═══════════════════════════════════════════════════════

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)  # 网格不需要AA

        # 1. 网格
        self._drawGrid(painter)

        # 2. 计算绘图区域
        left, top, right, bottom = self._margin
        plot_w = max(self.width() - left - right, 1)
        plot_h = max(self.height() - top - bottom, 1)
        plot_left = left
        plot_top = top
        plot_bottom = top + plot_h
        plot_right = left + plot_w

        painter.setClipRect(plot_left, plot_top, plot_w, plot_h)

        # 3. 遍历通道绘制波形
        for worker, color, visible in self._content.iter_draw_channels():
            if not visible:
                continue

            vmin = worker._envelope_vmin
            vmax = worker._envelope_vmax

            if len(vmin) == 0 or len(vmax) == 0:
                continue

            # 从包络缓存截取可见窗口
            offset = self._calcEnvelopeOffset(len(vmin), plot_w)
            vmin_win = vmin[offset:offset + plot_w]
            vmax_win = vmax[offset:offset + plot_w]
            actual = len(vmin_win)

            if actual == 0:
                continue

            # 坐标映射并绘制
            self._drawEnvelope(painter, vmin_win, vmax_win,
                               actual, plot_left, plot_bottom,
                               plot_w, plot_h, color)

        # 4. 阈值线
        if self._show_thresholds:
            self._drawThresholdLines(painter, plot_left, plot_right,
                                     plot_bottom, plot_h)

        painter.setClipping(False)
        painter.end()

    # ── 网格 ───────────────────────────────────────────

    def _drawGrid(self, painter: QPainter) -> None:
        """绘制缓存的网格"""
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        if self._grid_cache is None or self._grid_cache.size() != (w, h):
            self._grid_cache = QPixmap(w, h)
            self._grid_cache.fill(QColor(20, 20, 30))
            gp = QPainter(self._grid_cache)
            gp.setRenderHint(QPainter.Antialiasing, False)

            left, top, right, bottom = self._margin
            plot_w = w - left - right
            plot_h = h - top - bottom

            # 网格线颜色
            grid_pen = QPen(QColor(60, 60, 80), 1)
            grid_pen.setStyle(Qt.DotLine)
            gp.setPen(grid_pen)

            # 水平网格（10 条）
            for i in range(11):
                y = top + plot_h * i / 10
                gp.drawLine(int(left), int(y), int(w - right), int(y))

            # 垂直网格（10 条）
            for i in range(11):
                x = left + plot_w * i / 10
                gp.drawLine(int(x), int(top), int(x), int(h - bottom))

            # 中央十字线（实线）
            cross_pen = QPen(QColor(80, 80, 100), 1)
            gp.setPen(cross_pen)
            mid_x = left + plot_w / 2
            mid_y = top + plot_h / 2
            gp.drawLine(int(mid_x), int(top), int(mid_x), int(h - bottom))
            gp.drawLine(int(left), int(mid_y), int(w - right), int(mid_y))

            # 边框
            border_pen = QPen(QColor(100, 100, 120), 1)
            gp.setPen(border_pen)
            gp.drawRect(int(left), int(top), int(plot_w), int(plot_h))

            gp.end()

        painter.drawPixmap(0, 0, self._grid_cache)

    # ── 包络绘制 ──────────────────────────────────────

    def _calcEnvelopeOffset(self, env_len: int, plot_w: int) -> int:
        """计算包络缓存的可见窗口偏移"""
        if env_len <= plot_w:
            return 0
        # 对于简单实现，从缓存中间部分截取
        # 后续 scroll_offset 控制具体偏移
        return (env_len - plot_w) // 2

    def _drawEnvelope(self, painter: QPainter,
                      vmin: np.ndarray, vmax: np.ndarray,
                      n: int, plot_left: int, plot_bottom: int,
                      plot_w: int, plot_h: int,
                      color: QColor) -> None:
        """绘制单通道包络

        vmin/vmax 是已截取的可见窗口。
        当降采样时 vmin ≠ vmax（包络模式），不降采样时 vmin == vmax（折线模式）。
        """
        pen = QPen(color, self._line_width)
        painter.setPen(pen)

        half_range = self._y_range / 2.0
        y_center = self._y_offset

        # 批量构建 QLineF
        lines_min = []
        lines_max = []

        for i in range(n - 1):
            # X 坐标
            x1 = plot_left + plot_w * i / max(n - 1, 1)
            x2 = plot_left + plot_w * (i + 1) / max(n - 1, 1)

            # Y 坐标（vmin）
            v1_min = vmin[i]
            v2_min = vmin[i + 1]
            if not (np.isnan(v1_min) or np.isnan(v2_min)):
                y1_min = plot_bottom - (
                    (v1_min - (y_center - half_range)) / self._y_range) * plot_h
                y2_min = plot_bottom - (
                    (v2_min - (y_center - half_range)) / self._y_range) * plot_h
                lines_min.append(QLineF(x1, y1_min, x2, y2_min))

            # Y 坐标（vmax）
            v1_max = vmax[i]
            v2_max = vmax[i + 1]
            if not (np.isnan(v1_max) or np.isnan(v2_max)):
                y1_max = plot_bottom - (
                    (v1_max - (y_center - half_range)) / self._y_range) * plot_h
                y2_max = plot_bottom - (
                    (v2_max - (y_center - half_range)) / self._y_range) * plot_h
                lines_max.append(QLineF(x1, y1_max, x2, y2_max))

        if lines_min:
            painter.drawLines(lines_min)
        if lines_max:
            painter.drawLines(lines_max)

    # ── 阈值线 ────────────────────────────────────────

    def _drawThresholdLines(self, painter: QPainter,
                            plot_left: int, plot_right: int,
                            plot_bottom: int, plot_h: int) -> None:
        """绘制阈值虚线"""
        half_range = self._y_range / 2.0
        y_center = self._y_offset

        def value_to_y(value: float) -> float:
            return plot_bottom - (
                (value - (y_center - half_range)) / self._y_range) * plot_h

        # 上阈值（红色虚线）
        y_upper = value_to_y(self._upper_thresh)
        if 0 <= y_upper <= self.height():
            pen = QPen(QColor(255, 80, 80), 1)
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(int(plot_left), int(y_upper),
                             int(plot_right), int(y_upper))
            painter.drawText(int(plot_right) - 60, int(y_upper) - 4,
                             60, 16, Qt.AlignRight | Qt.AlignTop,
                             f"T+ {self._upper_thresh:.1f}")

        # 下阈值（橙色虚线）
        y_lower = value_to_y(self._lower_thresh)
        if 0 <= y_lower <= self.height():
            pen = QPen(QColor(255, 165, 0), 1)
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(int(plot_left), int(y_lower),
                             int(plot_right), int(y_lower))
            painter.drawText(int(plot_right) - 60, int(y_lower) + 4,
                             60, 16, Qt.AlignRight | Qt.AlignBottom,
                             f"T- {self._lower_thresh:.1f}")

    # ═══════════════════════════════════════════════════════
    # 阈值交互
    # ═══════════════════════════════════════════════════════

    def mouseDoubleClickEvent(self, event) -> None:
        """双击设阈值"""
        left = self._margin[0]
        if event.pos().x() < left:
            super().mouseDoubleClickEvent(event)
            return

        value = self._screenYToValue(event.pos().y())
        if event.modifiers() & Qt.ControlModifier:
            # Ctrl+双击 → 下阈值
            self._lower_thresh = value
            self.sig_lower_threshold_changed.emit(value)
        else:
            # 普通双击 → 上阈值
            self._upper_thresh = value
            self.sig_upper_threshold_changed.emit(value)
        self._show_thresholds = True
        self.update()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        """按下 → 检测是否靠近阈值线，进入拖拽"""
        if event.button() == Qt.LeftButton and self._show_thresholds:
            y = event.pos().y()
            y_upper = self._valueToScreenY(self._upper_thresh)
            y_lower = self._valueToScreenY(self._lower_thresh)

            if abs(y - y_upper) < 10:
                self._drag_target = "upper"
                self._drag_start_y = y
                self._drag_start_value = self._upper_thresh
                self.sig_threshold_drag_started.emit()
                return
            elif abs(y - y_lower) < 10:
                self._drag_target = "lower"
                self._drag_start_y = y
                self._drag_start_value = self._lower_thresh
                self.sig_threshold_drag_started.emit()
                return

        self._drag_target = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """移动 → 拖拽阈值线"""
        if self._drag_target is not None:
            dy = event.pos().y() - self._drag_start_y
            plot_h = max(self.height() - self._margin[1] - self._margin[3], 1)
            delta = -dy / plot_h * self._y_range
            new_value = self._drag_start_value + delta

            if self._drag_target == "upper":
                self._upper_thresh = new_value
                self.sig_upper_threshold_changed.emit(new_value)
            else:
                self._lower_thresh = new_value
                self.sig_lower_threshold_changed.emit(new_value)
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """释放 → 结束拖拽"""
        if self._drag_target is not None:
            self._drag_target = None
            self.sig_threshold_drag_finished.emit()
        super().mouseReleaseEvent(event)

    # ── 坐标工具 ──────────────────────────────────────

    def _screenYToValue(self, screen_y: int) -> float:
        """屏幕 Y 坐标 → 数据值"""
        _, top, _, bottom = self._margin
        plot_h = max(self.height() - top - bottom, 1)
        plot_bottom = top + plot_h
        half_range = self._y_range / 2.0
        y_center = self._y_offset

        rel_y = (plot_bottom - screen_y) / plot_h  # 0~1, bottom→top
        return y_center - half_range + rel_y * self._y_range

    def _valueToScreenY(self, value: float) -> float:
        """数据值 → 屏幕 Y 坐标"""
        _, top, _, bottom = self._margin
        plot_h = max(self.height() - top - bottom, 1)
        plot_bottom = top + plot_h
        half_range = self._y_range / 2.0
        y_center = self._y_offset

        return plot_bottom - (
            (value - (y_center - half_range)) / self._y_range) * plot_h
