"""
示波器 UI 和内容部件

包含：
    WaveformWidget          — 自定义波形绘制控件（带时间轴刻度 + gap 显示）
    OscilloscopeContent     — 内容部件（含工作线程管理 + 历史 RingBuffer）
"""
import json
import math
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel,
                             QSpinBox, QDoubleSpinBox, QPushButton, QWidget,
                             QSizePolicy, QScrollBar, QGroupBox, QCheckBox,
                             QFileDialog, QApplication)
from PyQt5.QtCore import Qt, QObject, pyqtSignal, pyqtSlot, QMetaObject, QThread
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QIcon

from conn_base import ConnNodeContentWidget
from conn_utils import ThreadManager
from .oscilloscope_core import OscilloscopeSampler, RingBuffer


# ═══════════════════════════════════════════════════════════════════════
# 波形绘制控件
# ═══════════════════════════════════════════════════════════════════════

class WaveformWidget(QWidget):
    """波形绘制控件 — 带视口交互：鼠标拖拽平移、滚轮缩放

    信号：
        panRequested(dx_data, dy_data) — 用户拖拽了 dx_data 个数据点、dy_data V
        zoomRequested(factor, cx_ratio, cy_ratio) — 用户请求缩放（中心在 plot 区域的 0-1 比例位置）
    """

    GRID_LINES = 4  # 水平和垂直网格线数量（5 个区间）
    MARGIN_L = 52
    MARGIN_R = 10
    MARGIN_T = 10
    MARGIN_B = 24

    # ── 颜色常量 ──
    BG_COLOR = QColor(0, 0, 0)
    GRID_COLOR = QColor(60, 60, 60)
    LABEL_COLOR = QColor(180, 180, 180)
    INFO_TIME_COLOR = QColor(100, 200, 255)
    INFO_VOLT_COLOR = QColor(240, 192, 64)

    # ── 静态绘图资源（类级别，初始化一次， paintEvent 复用引用） ──
    SMALL_FONT = QFont("monospace", 8)
    GRID_PEN = QPen(GRID_COLOR, 1)
    LABEL_PEN = QPen(LABEL_COLOR, 1)
    INFO_TIME_PEN = QPen(INFO_TIME_COLOR, 1)
    INFO_VOLT_PEN = QPen(INFO_VOLT_COLOR, 1)

    # ── 信号 ──
    panRequested = pyqtSignal(float, float)        # dx_data, dy_data
    zoomRequested = pyqtSignal(float, float, float)  # factor, cx_ratio(0-1), cy_ratio(0-1)

    @staticmethod
    def _nice_bounds(d_min: float, d_max: float, divisions: int = 4):
        """计算覆盖数据范围的人类友好型坐标轴范围"""
        raw_range = d_max - d_min
        if raw_range < 0.0001:
            return -0.5, 0.5, 0.25

        raw_step = raw_range / divisions
        exponent = math.floor(math.log10(raw_step))
        mantissa = raw_step / (10 ** exponent)

        if mantissa < 1.5:
            nice_step = 1.0
        elif mantissa < 3.5:
            nice_step = 2.0
        elif mantissa < 7.5:
            nice_step = 5.0
        else:
            nice_step = 10.0
        nice_step *= 10 ** exponent

        nice_min = math.floor(d_min / nice_step) * nice_step
        nice_max = math.ceil(d_max / nice_step) * nice_step

        if (nice_max - nice_min) / nice_step < divisions:
            nice_max = nice_min + nice_step * divisions

        return nice_min, nice_max, nice_step

    def __init__(self, parent=None):
        super().__init__(parent)
        # 数据
        self._data = []
        self._sampling_interval_us = 1000

        # 视口 Y 范围（由外部 OscilloscopeContent 管理 X 视口，Y 范围通知此 widget）
        self._view_y_min = -5.0
        self._view_y_max = 5.0

        # 用户设定的时间窗口（秒），用于网格标签，与实际数据量无关
        self._time_window_s = 1.0

        # 波形样式（动态，由外部控件驱动）
        self._wave_color = QColor(0, 220, 0)
        self._wave_line_width = 2

        # 拖拽状态
        self._dragging = False

        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    # ── 公共接口 ──────────────────────────────────────────────

    def setData(self, data: list[float], sampling_interval_us: int,
                time_window_s: float = 0.0):
        """设置波形数据并触发重绘（纯原始数据，不做加工）

        Args:
            data: 浮点数列表（含 NaN 魔法数字标记的 gap 点）
            sampling_interval_us: 采样间隔（微秒），用于时间标签计算
            time_window_s: 用户设定的时间窗口（秒），用于网格标签，与实际数据量无关
        """
        self._data = data
        if sampling_interval_us > 0:
            self._sampling_interval_us = sampling_interval_us
        if time_window_s > 0:
            self._time_window_s = time_window_s
        self.update()

    def setYRange(self, y_min: float, y_max: float):
        """设置 Y 轴显示范围"""
        if y_max <= y_min:
            return
        self._view_y_min = y_min
        self._view_y_max = y_max
        self.update()

    @property
    def plot_width(self) -> int:
        """获取绘图区域宽度（逻辑像素）"""
        return max(1, self.width() - self.MARGIN_L - self.MARGIN_R)

    @property
    def plot_height(self) -> int:
        """获取绘图区域高度（逻辑像素）"""
        return max(1, self.height() - self.MARGIN_T - self.MARGIN_B)

    def _screen_plot_width(self) -> int:
        """获取绘图区域在屏幕上的实际像素宽度（考虑 QGraphicsView 缩放）

        向上遍历 widget 层级找到 QGraphicsProxyWidget（WaveformWidget 不是直接被嵌入的，
        它的祖先 OscilloscopeContent 才是），然后计算：
        widget 逻辑像素 × sceneTransform × viewTransform = 屏幕物理像素。
        """
        # 向上查找 QGraphicsProxyWidget
        w = self
        proxy = None
        while w is not None:
            proxy = w.graphicsProxyWidget()
            if proxy is not None:
                break
            w = w.parentWidget()

        if proxy is None:
            return self.plot_width
        t = proxy.sceneTransform()
        scene = proxy.scene()
        if scene:
            views = scene.views()
            if views:
                vt = views[0].transform()
                scale = abs(t.m11() * vt.m11())
                return max(1, int(self.plot_width * scale))
        return max(1, int(self.plot_width * abs(t.m11())))

    # ── 格式化辅助 ────────────────────────────────────────────

    def _format_time_label(self, ms: float) -> str:
        if abs(ms) < 1:
            return f"{ms * 1000:.0f}μs"
        elif abs(ms) < 1000:
            return f"{ms:.0f}ms"
        else:
            return f"{ms / 1000:.2f}s"

    def _format_ms_per_div(self, ms_per_div: float) -> str:
        if ms_per_div < 1:
            return f"{ms_per_div * 1000:.0f}μs/div"
        elif ms_per_div < 1000:
            return f"{ms_per_div:.1f}ms/div"
        else:
            return f"{ms_per_div / 1000:.2f}s/div"

    # ── 波形样式设置 ──────────────────────────────────────────

    def setWaveColor(self, color: QColor):
        """设置波形线条颜色"""
        self._wave_color = QColor(color)
        self.update()

    def setWaveLineWidth(self, width: int):
        """设置波形线条宽度（px）"""
        self._wave_line_width = max(1, min(width, 10))
        self.update()

    # ── 鼠标交互 ──────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            px, py, pw, ph = (self.MARGIN_L, self.MARGIN_T,
                               self.plot_width, self.plot_height)
            if px <= event.x() <= px + pw and py <= event.y() <= py + ph:
                self._dragging = True
                self._drag_last_x = event.x()
                self._drag_last_y = event.y()
                self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._dragging and (event.buttons() & Qt.LeftButton):
            dx_px = event.x() - self._drag_last_x
            dy_px = event.y() - self._drag_last_y
            self._drag_last_x = event.x()
            self._drag_last_y = event.y()

            n = max(1, len(self._data))
            pw = self.plot_width
            ph = self.plot_height
            y_range = max(0.001, self._view_y_max - self._view_y_min)

            # 数据坐标增量（X：拖拽向右→看更旧数据→offset增大）
            dx_data = dx_px * n / pw
            dy_data = dy_px * y_range / ph

            self.panRequested.emit(dx_data, dy_data)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            self.setCursor(Qt.ArrowCursor)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        # delta/120 = 标准滚轮步数（±1/±2 等）
        factor = 1.15 ** (delta / 120)

        pw = self.plot_width
        ph = self.plot_height
        cx = (event.x() - self.MARGIN_L) / pw
        cy = 1.0 - (event.y() - self.MARGIN_T) / ph  # 屏幕 Y 反向

        self.zoomRequested.emit(factor, cx, cy)

    # ── 绘制 ──────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        margin_l, margin_r = self.MARGIN_L, self.MARGIN_R
        margin_t, margin_b = self.MARGIN_T, self.MARGIN_B
        plot_w = self.plot_width
        plot_h = self.plot_height

        if plot_w <= 0 or plot_h <= 0:
            painter.end()
            return

        # ── 背景 ──
        painter.fillRect(self.rect(), self.BG_COLOR)

        data = self._data
        n = len(data)
        y_min = self._view_y_min
        y_max = self._view_y_max
        d_range = y_max - y_min

        if n == 0 or d_range <= 0:
            painter.end()
            return

        # ── 水平网格线 + Y 轴标签（基于视口 Y 范围） ──
        painter.setFont(self.SMALL_FONT)
        for i in range(self.GRID_LINES + 1):
            y = int(margin_t + plot_h * i / self.GRID_LINES)
            painter.setPen(self.GRID_PEN)
            painter.drawLine(margin_l, y, margin_l + plot_w, y)

            normalized = 1.0 - i / self.GRID_LINES
            value = y_min + normalized * d_range
            if abs(value) < 0.0001:
                label = "0"
            elif abs(value) < 0.01:
                label = f"{value:.2e}"
            elif abs(value) < 100:
                label = f"{value:.3f}"
            else:
                label = f"{value:.1f}"
            painter.setPen(self.LABEL_PEN)
            painter.drawText(2, y - 6, margin_l - 6, 12,
                             Qt.AlignRight | Qt.AlignVCenter, label)

        # ── 垂直网格线 + X 轴时间标签 ──
        divs = self.GRID_LINES
        # 总时间跨度 = 用户设定的时间窗口，与实际数据量无关（保证网格稳定）
        total_time_ms = self._time_window_s * 1000.0
        ms_per_div = total_time_ms / divs if total_time_ms > 0 else 0.0

        for i in range(divs + 1):
            x = int(margin_l + plot_w * i / divs)
            painter.setPen(self.GRID_PEN)
            painter.drawLine(x, margin_t, x, margin_t + plot_h)

            if ms_per_div > 0:
                # 时间标签：右侧为"当前"，左侧为过去
                time_from_now = -(divs - i) * ms_per_div
                label = self._format_time_label(time_from_now)
                painter.setPen(self.LABEL_PEN)
                text_w = 42
                text_x = x - text_w // 2
                text_y = margin_t + plot_h + 4
                painter.drawText(text_x, text_y, text_w, 16,
                                 Qt.AlignCenter, label)

        # ── 右上角状态信息 ──
        info_y = margin_t + 2
        if ms_per_div > 0:
            painter.setPen(self.INFO_TIME_PEN)
            text = self._format_ms_per_div(ms_per_div)
            painter.drawText(margin_l + 4, info_y,
                             plot_w - 8, 14,
                             Qt.AlignRight | Qt.AlignTop, text)
            info_y += 16

        if d_range > 0:
            v_per_div = d_range / self.GRID_LINES
            painter.setPen(self.INFO_VOLT_PEN)
            text = f"{v_per_div:.4g}V/div"
            painter.drawText(margin_l + 4, info_y,
                             plot_w - 8, 14,
                             Qt.AlignRight | Qt.AlignTop, text)

        # ── 绘制波形 ──
        if n >= 2:
            # 时间轴映射：数据点 i 的时间 = i * interval_us（微秒）
            # 最右边的点（i=n-1）始终对齐右边缘，时间窗外的点被推到左侧屏幕外
            interval_us = self._sampling_interval_us
            total_time_us = max(1.0, self._time_window_s * 1_000_000)
            t_right = (n - 1) * interval_us  # 最右数据点的时间（微秒）

            screen_w = self._screen_plot_width()
            if n > screen_w * 3:
                # ── Min-max 抽取模式（数据点数 > 屏幕像素 ×3） ──
                # 抽取最多画 3×screen_w 条线，低于此阈值用逐点连线更高效
                ratio = n / screen_w
                prev_x = prev_max_y = prev_min_y = None

                wave_pen = QPen(self._wave_color, self._wave_line_width)
                painter.setPen(wave_pen)
                for col in range(screen_w):
                    i0 = int(col * ratio)
                    i1 = int((col + 1) * ratio)
                    chunk = data[i0:i1]
                    # NaN 是 gap 标记，必须过滤否则 min/max 返回 NaN
                    valid = [v for v in chunk if not math.isnan(v)]
                    if not valid:
                        prev_x = prev_max_y = prev_min_y = None
                        continue
                    vmin, vmax = min(valid), max(valid)
                    # X 坐标：用列中心的时间位置映射到像素，不依赖 n 均摊
                    t_col_center = (i0 + i1) / 2.0 * interval_us
                    x = int(margin_l + (1.0 + (t_col_center - t_right) / total_time_us) * plot_w)
                    y0 = int(margin_t + plot_h * (1.0 - (vmax - y_min) / d_range))
                    y1 = int(margin_t + plot_h * (1.0 - (vmin - y_min) / d_range))

                    # 竖线（列内 min→max）
                    painter.drawLine(x, y0, x, y1)
                    # 包络线（连前一列：max→max，min→min）
                    if prev_x is not None:
                        painter.drawLine(prev_x, prev_max_y, x, y0)
                        painter.drawLine(prev_x, prev_min_y, x, y1)
                    prev_x, prev_max_y, prev_min_y = x, y0, y1
            else:
                # ── 逐点连线模式（数据点数 ≤ 像素宽度，放大时平滑曲线） ──
                wave_pen = QPen(self._wave_color, self._wave_line_width)
                painter.setPen(wave_pen)
                for i in range(n - 1):
                    if math.isnan(data[i]) or math.isnan(data[i + 1]):
                        continue  # 任一端点是 gap → 跳过整段
                    # X 坐标：用实际时间位置映射，不依赖 n 均摊
                    t_i = i * interval_us
                    t_i1 = (i + 1) * interval_us
                    x0 = int(margin_l + (1.0 + (t_i - t_right) / total_time_us) * plot_w)
                    x1 = int(margin_l + (1.0 + (t_i1 - t_right) / total_time_us) * plot_w)
                    y0 = int(margin_t + plot_h * (1.0 - (data[i] - y_min) / d_range))
                    y1 = int(margin_t + plot_h * (1.0 - (data[i + 1] - y_min) / d_range))
                    painter.drawLine(x0, y0, x1, y1)

        painter.end()


# ═══════════════════════════════════════════════════════════════════════
# 示波器内容部件
# ═══════════════════════════════════════════════════════════════════════

class OscilloscopeContent(ConnNodeContentWidget):
    """
    示波器内容部件 — 管理工作线程、历史 RingBuffer、UI、渲染握手

    信号：
        renderComplete — 通知工作线程当前帧已渲染完成
    """
    renderComplete = pyqtSignal()
    _startRequested = pyqtSignal()
    _stopRequested = pyqtSignal()
    _clearRequested = pyqtSignal()

    class _Worker(QObject):
        """工作线程辅助对象"""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._isInit = False
            self.sampler: OscilloscopeSampler = None

        @pyqtSlot()
        def initSampler(self):
            if not self._isInit:
                self._isInit = True
                self.sampler = OscilloscopeSampler(self)

    # ── Y 轴 range+offset ↔ min/max 转换 ────────────────

    @property
    def _y_min(self):
        return self._y_offset - self._y_range / 2

    @property
    def _y_max(self):
        return self._y_offset + self._y_range / 2

    def _setYFromMinMax(self, y_min: float, y_max: float):
        """从 y_min/y_max 设置 range+offset"""
        self._y_range = y_max - y_min
        self._y_offset = (y_min + y_max) / 2

    def _syncVScrollbar(self):
        """同步垂直滚动条到当前 Y 偏移"""
        vr = max(0.001, self._y_range * 5)
        sv = int(self._y_offset / vr * 10000)
        sv = max(-10000, min(10000, sv))
        self._vScrollbar.blockSignals(True)
        self._vScrollbar.setValue(sv)
        self._vScrollbar.setEnabled(not self._yAutoCb.isChecked())
        self._vScrollbar.blockSignals(False)

    def initUI(self):
        # ── 工作线程初始化 ──
        self._worker = self.__class__._Worker()
        self._thread = QThread()
        self._thread.start()
        ThreadManager.instance().register_thread(self._thread)

        self._worker.moveToThread(self._thread)
        QMetaObject.invokeMethod(
            self._worker, "initSampler", Qt.BlockingQueuedConnection
        )
        self.sampler: OscilloscopeSampler = self._worker.sampler

        # ── 主线程历史数据缓存 ──
        self._history_rb = RingBuffer(100000)

        # ── 视口状态（数据坐标） ──
        self._view_offset = 0       # X 偏移：从最新数据往回偏移的数据点数（0=最新）
        self._time_window_s = 1.0   # 时间窗口（秒）— 主参数，与采样间隔无关
        self._view_count = 1000     # X 范围：可见窗口包含的数据点数（由 _time_window_s 和 interval 导出）
        self._y_range = 10.0        # Y 范围：幅值跨度
        self._y_offset = 0.0        # Y 偏移：幅值中心位置
        self._sampling_interval_us = 1000

        # ── UI 布局 ──
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)

        # ── 波形显示 + 垂直滚动条 ──
        waveform_row = QHBoxLayout()
        waveform_row.setContentsMargins(0, 0, 0, 0)
        waveform_row.setSpacing(0)
        self._waveform = WaveformWidget()
        waveform_row.addWidget(self._waveform, stretch=1)
        self._vScrollbar = QScrollBar(Qt.Vertical)
        self._vScrollbar.setRange(-10000, 10000)
        self._vScrollbar.setValue(0)
        self._vScrollbar.setFixedWidth(12)
        self._vScrollbar.setEnabled(False)
        waveform_row.addWidget(self._vScrollbar)
        layout.addLayout(waveform_row)

        # ── 水平滚动条 ──
        self._scrollbar = QScrollBar(Qt.Horizontal)
        self._scrollbar.setMinimum(0)
        self._scrollbar.setMaximum(0)
        self._scrollbar.setValue(0)
        layout.addWidget(self._scrollbar)

        # ── 采集系统 ──
        self._acqGroup = QGroupBox("采集")
        self._acqGroup.setObjectName("acqGroup")
        acq_grid = QHBoxLayout(self._acqGroup)
        acq_grid.setContentsMargins(6, 2, 6, 4)
        acq_grid.setSpacing(6)

        acq_grid.addWidget(QLabel("FPS:"))
        self._fpsSpin = QSpinBox()
        self._fpsSpin.setRange(1, 120)
        self._fpsSpin.setValue(30)
        self._fpsSpin.setFixedWidth(60)
        acq_grid.addWidget(self._fpsSpin)

        acq_grid.addWidget(QLabel("Buffer:"))
        self._bufferSpin = QSpinBox()
        self._bufferSpin.setRange(10, 5000000)
        self._bufferSpin.setValue(100000)
        self._bufferSpin.setSingleStep(1000)
        self._bufferSpin.setFixedWidth(75)
        acq_grid.addWidget(self._bufferSpin)

        acq_grid.addWidget(QLabel("Temp:"))
        self._tempBufferSpin = QSpinBox()
        self._tempBufferSpin.setRange(10, 100000)
        self._tempBufferSpin.setValue(5000)
        self._tempBufferSpin.setSingleStep(500)
        self._tempBufferSpin.setFixedWidth(65)
        acq_grid.addWidget(self._tempBufferSpin)

        acq_grid.addWidget(QLabel("采样频率:"))
        self._sampleFreqSpin = QDoubleSpinBox()
        self._sampleFreqSpin.setRange(1, 10000000)
        self._sampleFreqSpin.setValue(1000)
        self._sampleFreqSpin.setDecimals(0)
        self._sampleFreqSpin.setSuffix(" Hz")
        self._sampleFreqSpin.setFixedWidth(95)
        self._sampleFreqSpin.setToolTip("默认采样频率（数据包含频率时自动同步）")
        acq_grid.addWidget(self._sampleFreqSpin)

        acq_grid.addStretch()
        layout.addWidget(self._acqGroup)

        # ── 水平系统（时间轴） ──
        self._hGroup = QGroupBox("水平系统")
        self._hGroup.setObjectName("hGroup")
        h_grid = QHBoxLayout(self._hGroup)
        h_grid.setContentsMargins(6, 2, 6, 4)
        h_grid.setSpacing(6)

        h_grid.addWidget(QLabel("时间窗口:"))
        self._timeWindowSpin = QDoubleSpinBox()
        self._timeWindowSpin.setRange(0.0001, 10000.0)
        self._timeWindowSpin.setValue(1.0)
        self._timeWindowSpin.setDecimals(4)
        self._timeWindowSpin.setSingleStep(0.01)
        self._timeWindowSpin.setSuffix(" s")
        self._timeWindowSpin.setFixedWidth(90)
        h_grid.addWidget(self._timeWindowSpin)

        h_grid.addStretch()

        layout.addWidget(self._hGroup)

        # ── 垂直系统（幅值轴） ──
        self._vGroup = QGroupBox("垂直系统")
        self._vGroup.setObjectName("vGroup")
        v_main = QVBoxLayout(self._vGroup)
        v_main.setContentsMargins(6, 2, 6, 2)
        v_main.setSpacing(2)

        # 自动范围 + Y 范围 + Y 偏移
        y_range_row = QHBoxLayout()
        y_range_row.setSpacing(4)
        self._yAutoCb = QCheckBox("自动")
        self._yAutoCb.setChecked(True)
        self._yAutoCb.setStyleSheet("color: #f0c040; border: none;")
        y_range_row.addWidget(self._yAutoCb)

        y_range_row.addWidget(QLabel("Y 范围:"))
        self._yRangeSpin = QDoubleSpinBox()
        self._yRangeSpin.setRange(0.0001, 20000.0)
        self._yRangeSpin.setValue(10.0)
        self._yRangeSpin.setDecimals(4)
        self._yRangeSpin.setFixedWidth(85)
        self._yRangeSpin.setEnabled(False)
        y_range_row.addWidget(self._yRangeSpin)

        y_range_row.addWidget(QLabel("Y 偏移:"))
        self._yOffsetSpin = QDoubleSpinBox()
        self._yOffsetSpin.setRange(-50000.0, 50000.0)
        self._yOffsetSpin.setValue(0.0)
        self._yOffsetSpin.setDecimals(4)
        self._yOffsetSpin.setFixedWidth(85)
        self._yOffsetSpin.setEnabled(False)
        y_range_row.addWidget(self._yOffsetSpin)

        y_range_row.addStretch()
        v_main.addLayout(y_range_row)

        # 波形样式行
        style_row = QHBoxLayout()
        style_row.setSpacing(4)
        style_row.addWidget(QLabel("线宽:"))
        self._lineWidthSpin = QSpinBox()
        self._lineWidthSpin.setRange(1, 10)
        self._lineWidthSpin.setValue(2)
        self._lineWidthSpin.setFixedWidth(50)
        self._lineWidthSpin.setToolTip("波形线条宽度（1-10 px）")
        style_row.addWidget(self._lineWidthSpin)

        style_row.addWidget(QLabel("颜色:"))
        # 预置颜色色块（内联，不受全局 QSS 影响），避免 QColorDialog 在 QGraphicsView 中白屏
        self._colorSwatches = []
        self._activeSwatchIdx = 0
        self._swatchColorMap = {}  # color_hex → swatch_index
        preset_colors = [
            "#00dc00",  # 绿（默认）
            "#a0cc00",  # 黄绿
            "#cccc00",  # 黄
            "#cc8800",  # 橙
            "#cc4444",  # 红
            "#cc44cc",  # 紫
            "#00aacc",  # 青
            "#4488ff",  # 蓝
            "#e0e0e0",  # 白
        ]
        for i, hex_color in enumerate(preset_colors):
            btn = QPushButton()
            btn.setFixedSize(20, 20)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(f"波形颜色: {hex_color}")
            btn.setStyleSheet(
                f"background-color: {hex_color};"
                "border: 1px solid #505050; border-radius: 3px;"
                "min-height: 20px; min-width: 20px; padding: 0px;"
            )
            btn.clicked.connect(
                lambda checked, idx=i, c=hex_color: self._onSwatchClicked(idx, c))
            style_row.addWidget(btn)
            self._colorSwatches.append((btn, hex_color))
            self._swatchColorMap[hex_color] = i
        self._updateSwatchHighlight(0)  # 默认高亮绿色

        style_row.addStretch()
        v_main.addLayout(style_row)

        layout.addWidget(self._vGroup)

        # ── 操作栏 ──
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self._startBtn = QPushButton("Start")
        self._startBtn.setCheckable(True)
        self._startBtn.setFixedWidth(65)
        action_row.addWidget(self._startBtn)

        self._clearBtn = QPushButton("清空")
        self._clearBtn.setIcon(QIcon("icons/sub_2.png"))
        self._clearBtn.setFixedWidth(55)
        action_row.addWidget(self._clearBtn)

        self._saveBtn = QPushButton("保存")
        self._saveBtn.setFixedWidth(55)
        action_row.addWidget(self._saveBtn)

        action_row.addStretch()

        layout.addLayout(action_row)

        # ── 整体样式 ──
        self._applyStyleSheet()

        # ── 信号连接 ──
        self._connectSignals()

        self.resize(560, 420)

    def _applyStyleSheet(self):
        """应用暗色主题样式"""
        self.setStyleSheet("""
            OscilloscopeContent {
                background-color: #0a0a0a;
            }
            QGroupBox {
                font-size: 11px;
                font-weight: bold;
                color: #e0e0e0;
                border: 1px solid #404040;
                border-radius: 4px;
                margin-top: 8px;
                padding: 10px 4px 4px 4px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                color: #c0c0c0;
            }
            #acqGroup {
                border-color: #2a6a9a;
            }
            #acqGroup::title {
                color: #5aadff;
            }
            #hGroup {
                border-color: #2a7a7a;
            }
            #hGroup::title {
                color: #4adcdc;
            }
            #vGroup {
                border-color: #8a6a2a;
            }
            #vGroup::title {
                color: #f0c040;
            }
            QSpinBox, QDoubleSpinBox {
                background-color: #202020;
                color: #e0e0e0;
                border: 1px solid #404040;
                padding: 2px 4px;
                min-height: 20px;
            }
            QSpinBox::up-button, QDoubleSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 18px;
                background-color: #353535;
                border: 1px solid #505050;
                border-left: none;
                border-bottom: none;
                border-top-right-radius: 3px;
            }
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 18px;
                background-color: #353535;
                border: 1px solid #505050;
                border-left: none;
                border-top: none;
                border-bottom-right-radius: 3px;
            }
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
                width: 0;
                height: 0;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 5px solid white;
            }
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
                width: 0;
                height: 0;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid white;
            }
            QPushButton {
                background-color: #303030;
                color: #e0e0e0;
                border: 1px solid #505050;
                padding: 3px 8px;
                min-height: 22px;
            }
            QPushButton:checked {
                background-color: #005000;
                color: #00ff00;
                border: 1px solid #00ff00;
            }
            QScrollBar:horizontal {
                background: #101010;
                height: 10px;
                border: 1px solid #303030;
            }
            QScrollBar::handle:horizontal {
                background: #404040;
                min-width: 30px;
                border-radius: 3px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar:vertical {
                background: #101010;
                width: 10px;
                border: 1px solid #303030;
            }
            QScrollBar::handle:vertical {
                background: #404040;
                min-height: 30px;
                border-radius: 3px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

    def _connectSignals(self):
        """连接所有信号"""
        # ── 工作线程数据 ──
        self.sampler.frameReady.connect(self._onFrameReady)
        self.renderComplete.connect(self.sampler.onRenderComplete)

        # ── 控制桥接（跨线程） ──
        self._startRequested.connect(self.sampler.start)
        self._stopRequested.connect(self.sampler.stop)
        self._clearRequested.connect(self.sampler.clear)
        self._fpsSpin.valueChanged.connect(self.sampler.setFps)
        self._tempBufferSpin.valueChanged.connect(self.sampler.setTempBufferSize)

        # ── 本地参数（主线程控制） ──
        self._bufferSpin.valueChanged.connect(self._onBufferSizeChanged)
        self._timeWindowSpin.valueChanged.connect(self._onTimeWindowChanged)
        self._scrollbar.valueChanged.connect(self._onScrollChanged)

        # ── 波形视口交互 ──
        self._waveform.panRequested.connect(self._onWaveformPan)
        self._waveform.zoomRequested.connect(self._onWaveformZoom)

        # ── Y 范围控制 ──
        self._yAutoCb.toggled.connect(self._onYAutoToggled)
        self._yRangeSpin.valueChanged.connect(self._onYRangeSpinChanged)
        self._yOffsetSpin.valueChanged.connect(self._onYOffsetSpinChanged)
        self._vScrollbar.valueChanged.connect(self._onVScrollChanged)

        # ── 采样频率 ──
        self._sampleFreqSpin.valueChanged.connect(self._onSampleFreqChanged)

        # ── 波形样式 ──
        self._lineWidthSpin.valueChanged.connect(self._waveform.setWaveLineWidth)

        # ── UI 控件 ──
        self._startBtn.clicked.connect(self._onStartClicked)
        self._clearBtn.clicked.connect(self._onClearClicked)
        self._saveBtn.clicked.connect(self._onSaveClicked)

    # ── 渲染 ───────────────────────────────────────────

    def _render_frame(self):
        """从历史 RingBuffer 读取视口对应的数据，无加工地传给 WaveformWidget 绘制

        NaN 魔法数字（gap 标记）已直接在历史缓冲区中，
        WaveformWidget 检测到 NaN 后跳过整段不画。
        """
        total = self._history_rb.count
        if total <= 0 or self._sampling_interval_us <= 0:
            self._waveform.setData([], self._sampling_interval_us)
            return

        # 裁剪视口到有效范围
        vc = int(max(1, min(self._view_count, total)))
        max_offset = max(0, total - vc)
        view_offset = int(max(0, min(self._view_offset, max_offset)))

        # 从 RingBuffer 读取窗口数据（原始数据，无加工）
        data, _, scrollbar_max, _ = \
            self._history_rb.read_frame(vc, view_offset)

        if not data:
            self._waveform.setData([], self._sampling_interval_us)
            return

        # 是否在末尾（自动跟随）
        at_end = (view_offset <= 0)

        # 更新滚动条
        self._scrollbar.blockSignals(True)
        self._scrollbar.setMaximum(scrollbar_max)
        if at_end:
            self._scrollbar.setValue(scrollbar_max)
            self._view_offset = 0
        else:
            self._scrollbar.setValue(scrollbar_max - view_offset)
        self._scrollbar.blockSignals(False)

        # 计算 Y 范围（range+offset 模型）
        if self._yAutoCb.isChecked():
            valid = [v for v in data if not math.isnan(v)]
            if len(valid) >= 2:
                y_min, y_max, _ = WaveformWidget._nice_bounds(
                    min(valid), max(valid))
            else:
                y_min, y_max = -1.0, 1.0
            self._setYFromMinMax(y_min, y_max)
            # 同步 Y spinbox
            self._yRangeSpin.blockSignals(True)
            self._yOffsetSpin.blockSignals(True)
            self._yRangeSpin.setValue(self._y_range)
            self._yOffsetSpin.setValue(self._y_offset)
            self._yRangeSpin.blockSignals(False)
            self._yOffsetSpin.blockSignals(False)
        else:
            y_min = self._y_min
            y_max = self._y_max

        # 同步垂直滚动条
        self._syncVScrollbar()

        # 纯原始数据发送到波形显示（无 amp/offset 加工）
        self._waveform.setData(data, self._sampling_interval_us, self._time_window_s)
        self._waveform.setYRange(y_min, y_max)

    # ── 槽函数 ─────────────────────────────────────────

    @pyqtSlot(list, int, float)
    def _onFrameReady(self, data, _gap_count, sampling_interval_us):
        """收到工作线程的数据 chunk — 直接写入历史缓冲区（含 NaN 魔法数字）"""
        # 只在数据提供了有效采样间隔且不同于当前值时更新（避免 UI 闪烁）
        if sampling_interval_us > 0 and sampling_interval_us != self._sampling_interval_us:
            self._sampling_interval_us = sampling_interval_us
            # 采样间隔变了 → 重新导出可见点数，保持时间窗口不变
            self._view_count = self._countFromTimeWindow()
            # 自动同步采样频率 spinbox（Hz）
            freq_hz = 1_000_000.0 / max(1, sampling_interval_us)
            self._sampleFreqSpin.blockSignals(True)
            self._sampleFreqSpin.setValue(freq_hz)
            self._sampleFreqSpin.blockSignals(False)

        if not data:
            self.renderComplete.emit()
            return

        # 写入历史缓冲区
        self._history_rb.write_batch(data)

        # 渲染当前帧
        self._render_frame()

        # 通知工作线程：渲染完成
        self.renderComplete.emit()

    def _onBufferSizeChanged(self, size: int):
        """调整历史 RingBuffer 大小"""
        self._history_rb.resize(max(100, size))
        self._render_frame()

    def _onTimeWindowChanged(self, value: float):
        """时间窗口 spinbox 改变 → 设置主参数，重新导出可见点数"""
        self._time_window_s = max(0.001, value)
        self._view_count = self._countFromTimeWindow()
        self._render_frame()

    def _countFromTimeWindow(self):
        """从时间窗口（秒）和采样间隔导出可见数据点数"""
        return max(10, int(self._time_window_s * 1_000_000 / max(1, self._sampling_interval_us)))

    def _onScrollChanged(self, value: int):
        """滚动条改变 → 更新视口 offset"""
        total = self._history_rb.count
        if total <= 0:
            return
        max_offset = max(0, total - self._view_count)
        self._view_offset = max(0, max_offset - value)
        self._render_frame()

    def _onYAutoToggled(self, checked):
        self._yRangeSpin.setEnabled(not checked)
        self._yOffsetSpin.setEnabled(not checked)
        self._vScrollbar.setEnabled(not checked)
        self._render_frame()

    def _onYRangeSpinChanged(self, value: float):
        """Y 范围 spinbox 变化 → 更新 _y_range"""
        if not self._yAutoCb.isChecked():
            self._y_range = max(0.001, value)
        self._render_frame()

    def _onYOffsetSpinChanged(self, value: float):
        """Y 偏移 spinbox 变化 → 更新 _y_offset"""
        if not self._yAutoCb.isChecked():
            self._y_offset = value
        self._render_frame()

    def _onVScrollChanged(self, value: int):
        """垂直滚动条变化 → 更新 _y_offset"""
        if not self._yAutoCb.isChecked():
            vr = max(0.001, self._y_range * 5)
            self._y_offset = value / 10000.0 * vr
        self._render_frame()

    def _onSampleFreqChanged(self, freq_hz: float):
        """用户手动设置采样频率 → 更新采样间隔（备用默认值）"""
        interval_us = int(1_000_000.0 / max(1, freq_hz))
        if interval_us != self._sampling_interval_us:
            self._sampling_interval_us = interval_us
            self._view_count = self._countFromTimeWindow()
            self._render_frame()

    def _updateSwatchHighlight(self, active_idx: int):
        """更新色块高亮状态：active_idx 边框加亮，其余恢复"""
        for i, (btn, hex_color) in enumerate(self._colorSwatches):
            if i == active_idx:
                btn.setStyleSheet(
                    f"background-color: {hex_color};"
                    "border: 2px solid #ffffff; border-radius: 3px;"
                    "min-height: 20px; min-width: 20px; padding: 0px;"
                )
            else:
                btn.setStyleSheet(
                    f"background-color: {hex_color};"
                    "border: 1px solid #505050; border-radius: 3px;"
                    "min-height: 20px; min-width: 20px; padding: 0px;"
                )

    def _onSwatchClicked(self, idx: int, hex_color: str):
        """色块点击 → 切换波形颜色"""
        self._waveform.setWaveColor(QColor(hex_color))
        self._activeSwatchIdx = idx
        self._updateSwatchHighlight(idx)

    def setWaveColorFromHex(self, hex_color: str):
        """从十六进制颜色字符串设置波形颜色（供反序列化调用）"""
        color = QColor(hex_color)
        if color.isValid():
            self._waveform.setWaveColor(color)
            # 尝试匹配预置色块
            idx = self._swatchColorMap.get(hex_color, -1)
            if idx >= 0:
                self._activeSwatchIdx = idx
                self._updateSwatchHighlight(idx)

    # ── 视口交互 ───────────────────────────────────────

    def _onWaveformPan(self, dx_data: float, dy_data: float):
        """鼠标拖拽平移视口 — 改变 X offset 和 Y offset"""
        total = self._history_rb.count
        if total <= 0:
            return

        # X 方向平移（改变 _view_offset，即 X offset）
        max_offset = max(0, total - self._view_count)
        self._view_offset = int(max(0, min(self._view_offset + dx_data, max_offset)))

        # Y 方向平移（改变 _y_offset，保持 _y_range 不变）
        if dy_data != 0 and self._yAutoCb.isChecked():
            self._yAutoCb.setChecked(False)
        self._y_offset += dy_data

        self._render_frame()

    def _onWaveformZoom(self, factor: float, cx_ratio: float, cy_ratio: float):
        """滚轮缩放视口

        无修饰键 → X 轴缩放（时间轴 range）
        Ctrl+滚轮 → Y 轴缩放（幅值 range）

        Args:
            factor: >1 放大，<1 缩小
            cx_ratio: 缩放中心在 plot 区域的水平比例 (0-1)
            cy_ratio: 缩放中心在 plot 区域的垂直比例 (0-1，从下到上)
        """
        total = self._history_rb.count
        if total <= 0:
            return

        modifiers = QApplication.keyboardModifiers()

        if modifiers & Qt.ControlModifier:
            # ── Y 轴缩放（Ctrl+wheel — 改变 _y_range） ──
            self._yAutoCb.setChecked(False)
            # 光标处的数据值
            vy = self._y_offset + (cy_ratio - 0.5) * self._y_range
            old_range = self._y_range
            self._y_range = max(0.001, old_range / factor)
            # 调整 offset 保持光标位置不变
            self._y_offset = vy - (cy_ratio - 0.5) * self._y_range
        else:
            # ── X 轴缩放（wheel — 改变时间窗口） ──
            self._time_window_s = max(0.001, self._time_window_s / factor)
            self._timeWindowSpin.blockSignals(True)
            self._timeWindowSpin.setValue(self._time_window_s)
            self._timeWindowSpin.blockSignals(False)
            self._view_count = self._countFromTimeWindow()
            new_count = self._view_count
            full_cx = self._view_offset + cx_ratio * self._view_count
            self._view_offset = int(full_cx - cx_ratio * new_count)
            max_offset = max(0, total - new_count)
            self._view_offset = max(0, min(self._view_offset, max_offset))

        self._render_frame()

    def _onStartClicked(self, checked):
        """启动/停止工作线程的帧定时器"""
        if checked:
            self._startRequested.emit()
            self._startBtn.setText("Stop")
        else:
            self._stopRequested.emit()
            self._startBtn.setText("Start")

    def _onClearClicked(self):
        """清空显示和缓存"""
        self._history_rb.clear()
        self._waveform.setData([], self._sampling_interval_us)
        self._clearRequested.emit()

    def _onSaveClicked(self):
        """将所有历史数据保存为 JSON 文件（dict 格式）"""
        data = self._history_rb.get_all_ordered()
        if not data:
            return

        fp, _ = QFileDialog.getSaveFileName(
            self, "保存波形数据", "",
            "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not fp:
            return

        record = {
            "点": data,
            "采样间隔_us": self._sampling_interval_us,
            "gap数": 0,
        }
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

    def cleanup(self):
        """清理工作线程和资源"""
        self._stopRequested.emit()
        self._worker.deleteLater()
        self._thread.quit()
        self._thread.wait(3000)
        self._thread.deleteLater()
