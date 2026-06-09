"""
示波器 UI 和内容部件

包含：
    WaveformWidget          — 自定义波形绘制控件（带时间轴刻度 + gap 显示）
    OscilloscopeContent     — 内容部件（含工作线程管理 + 历史 RingBuffer）
"""
import math
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel,
                             QSpinBox, QDoubleSpinBox, QPushButton, QWidget,
                             QSizePolicy, QScrollBar, QGroupBox, QCheckBox)
from PyQt5.QtCore import Qt, QObject, pyqtSignal, pyqtSlot, QMetaObject, QThread
from PyQt5.QtGui import QPainter, QPen, QColor, QFont

from conn_base import ConnNodeContentWidget
from conn_utils import ThreadManager
from .oscilloscope_core import OscilloscopeSampler, RingBuffer


# ═══════════════════════════════════════════════════════════════════════
# 波形绘制控件
# ═══════════════════════════════════════════════════════════════════════

class WaveformWidget(QWidget):
    """自定义波形绘制控件 — 显示数据曲线 + 网格 + 时间轴 + 覆盖标记 + gap"""

    GRID_LINES = 4  # 水平和垂直网格线数量（5 个区间）

    # ── 颜色常量 ──
    BG_COLOR = QColor(0, 0, 0)
    GRID_COLOR = QColor(60, 60, 60)
    LABEL_COLOR = QColor(180, 180, 180)
    INFO_TIME_COLOR = QColor(100, 200, 255)
    INFO_VOLT_COLOR = QColor(240, 192, 64)
    WAVE_COLOR = QColor(0, 220, 0)

    # ── 静态绘图资源（类级别，初始化一次，paintEvent 复用引用） ──
    SMALL_FONT = QFont("monospace", 8)
    GRID_PEN = QPen(GRID_COLOR, 1)
    LABEL_PEN = QPen(LABEL_COLOR, 1)
    INFO_TIME_PEN = QPen(INFO_TIME_COLOR, 1)
    INFO_VOLT_PEN = QPen(INFO_VOLT_COLOR, 1)
    WAVE_PEN = QPen(WAVE_COLOR, 2)           # 绿色波形线

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
        self._data = []
        self._ms_per_div = 0.0
        # Y 范围控制
        self._y_auto = True
        self._y_min = None
        self._y_max = None
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def setYRange(self, y_min=None, y_max=None, auto=True):
        """设置 Y 轴显示范围"""
        self._y_auto = auto
        if not auto:
            self._y_min = y_min if y_min is not None else -5.0
            self._y_max = y_max if y_max is not None else 5.0
        else:
            self._y_min = None
            self._y_max = None
        self.update()

    def setData(self, data, ms_per_div):
        """设置数据并触发重绘

        Args:
            data: 浮点数列表（包含 NaN 魔法数字标记的 gap 点）
            ms_per_div: 每格毫秒数
        """
        self._data = data
        self._ms_per_div = ms_per_div
        self.update()

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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        margin_l = 52
        margin_r = 10
        margin_t = 10
        margin_b = 24
        plot_w = w - margin_l - margin_r
        plot_h = h - margin_t - margin_b

        if plot_w <= 0 or plot_h <= 0:
            painter.end()
            return

        # ── 背景 ──
        painter.fillRect(self.rect(), self.BG_COLOR)

        # ── 数据统计 ──
        n = len(self._data)
        total_units = n

        # ── 计算 Y 轴范围 ──
        if n >= 2 and self._y_auto:
            valid_vals = [v for v in self._data if not math.isnan(v)]
            if len(valid_vals) >= 2:
                d_min = min(valid_vals)
                d_max = max(valid_vals)
                y_min, y_max, _ = self._nice_bounds(d_min, d_max, self.GRID_LINES)
            else:
                y_min, y_max = -1.0, 1.0
        elif n >= 2 and not self._y_auto:
            y_min = self._y_min
            y_max = self._y_max
            if y_max <= y_min:
                y_min, y_max = -5.0, 5.0
        else:
            y_min, y_max = -1.0, 1.0
        d_range = y_max - y_min

        # ── 水平网格线 + Y 轴标签 ──
        painter.setFont(self.SMALL_FONT)
        for i in range(self.GRID_LINES + 1):
            y = int(margin_t + plot_h * i / self.GRID_LINES)
            painter.setPen(self.GRID_PEN)
            painter.drawLine(margin_l, y, margin_l + plot_w, y)

            if d_range > 0:
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
        for i in range(divs + 1):
            x = int(margin_l + plot_w * i / divs)
            painter.setPen(self.GRID_PEN)
            painter.drawLine(x, margin_t, x, margin_t + plot_h)

            if self._ms_per_div > 0:
                time_from_now = -(divs - i) * self._ms_per_div
                label = self._format_time_label(time_from_now)
                painter.setPen(self.LABEL_PEN)
                text_w = 42
                text_x = x - text_w // 2
                text_y = margin_t + plot_h + 4
                painter.drawText(text_x, text_y, text_w, 16,
                                 Qt.AlignCenter, label)

        # ── 右上角状态信息 ──
        info_y = margin_t + 2
        if self._ms_per_div > 0:
            painter.setPen(self.INFO_TIME_PEN)
            text = self._format_ms_per_div(self._ms_per_div)
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

        # ── 逐线段绘制波形（遇 gap 点直接跳过，不画假数据） ──
        if n >= 2:
            for i in range(n - 1):
                if math.isnan(self._data[i]) or math.isnan(self._data[i + 1]):
                    continue  # 任一端点是 gap → 跳过整段
                x0 = int(margin_l + (i / total_units) * plot_w)
                x1 = int(margin_l + ((i + 1) / total_units) * plot_w)
                y0 = int(margin_t + plot_h * (1.0 - (self._data[i] - y_min) / d_range))
                y1 = int(margin_t + plot_h * (1.0 - (self._data[i + 1] - y_min) / d_range))
                painter.setPen(self.WAVE_PEN)
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

        # ── 显示参数（从工作线程移回主线程） ──
        self._amplification = 1.0
        self._offset = 0.0
        self._time_window_s = 1.0
        self._sampling_interval_us = 1000
        self._scrollbar_value = 10 ** 9  # 默认最新

        # ── UI 布局 ──
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)

        # ── 波形显示 ──
        self._waveform = WaveformWidget()
        layout.addWidget(self._waveform)

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
        self._bufferSpin.setRange(100, 1000000)
        self._bufferSpin.setValue(100000)
        self._bufferSpin.setSingleStep(1000)
        self._bufferSpin.setFixedWidth(75)
        acq_grid.addWidget(self._bufferSpin)

        acq_grid.addWidget(QLabel("Temp:"))
        self._tempBufferSpin = QSpinBox()
        self._tempBufferSpin.setRange(100, 50000)
        self._tempBufferSpin.setValue(5000)
        self._tempBufferSpin.setSingleStep(500)
        self._tempBufferSpin.setFixedWidth(65)
        acq_grid.addWidget(self._tempBufferSpin)

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
        self._timeWindowSpin.setRange(0.01, 60.0)
        self._timeWindowSpin.setValue(1.0)
        self._timeWindowSpin.setDecimals(2)
        self._timeWindowSpin.setSingleStep(0.1)
        self._timeWindowSpin.setSuffix(" s")
        self._timeWindowSpin.setFixedWidth(90)
        h_grid.addWidget(self._timeWindowSpin)

        h_grid.addStretch()

        h_grid.addWidget(QLabel("时间/格:"))
        self._timePerDivLabel = QLabel("---")
        self._timePerDivLabel.setFixedWidth(100)
        self._timePerDivLabel.setAlignment(Qt.AlignCenter)
        self._timePerDivLabel.setStyleSheet(
            "color: #64c8ff; border: none; font-size: 12px; font-weight: bold;"
        )
        h_grid.addWidget(self._timePerDivLabel)

        layout.addWidget(self._hGroup)

        # ── 垂直系统（幅值轴） ──
        self._vGroup = QGroupBox("垂直系统")
        self._vGroup.setObjectName("vGroup")
        v_main = QVBoxLayout(self._vGroup)
        v_main.setContentsMargins(6, 2, 6, 2)
        v_main.setSpacing(2)

        # 第1行：自动范围 + Y 下限 + Y 上限
        y_range_row = QHBoxLayout()
        y_range_row.setSpacing(4)
        self._yAutoCb = QCheckBox("自动")
        self._yAutoCb.setChecked(True)
        self._yAutoCb.setStyleSheet("color: #f0c040; border: none;")
        y_range_row.addWidget(self._yAutoCb)

        y_range_row.addWidget(QLabel("Y下限:"))
        self._yMinSpin = QDoubleSpinBox()
        self._yMinSpin.setRange(-10000.0, 10000.0)
        self._yMinSpin.setValue(-5.0)
        self._yMinSpin.setDecimals(3)
        self._yMinSpin.setFixedWidth(85)
        self._yMinSpin.setEnabled(False)
        y_range_row.addWidget(self._yMinSpin)

        y_range_row.addWidget(QLabel("Y上限:"))
        self._yMaxSpin = QDoubleSpinBox()
        self._yMaxSpin.setRange(-10000.0, 10000.0)
        self._yMaxSpin.setValue(5.0)
        self._yMaxSpin.setDecimals(3)
        self._yMaxSpin.setFixedWidth(85)
        self._yMaxSpin.setEnabled(False)
        y_range_row.addWidget(self._yMaxSpin)

        y_range_row.addStretch()
        v_main.addLayout(y_range_row)

        # 第2行：放大倍数 + 偏移
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)
        ctrl_row.addWidget(QLabel("放大倍数:"))
        self._ampSpin = QDoubleSpinBox()
        self._ampSpin.setRange(0.01, 1000.0)
        self._ampSpin.setValue(1.0)
        self._ampSpin.setDecimals(3)
        self._ampSpin.setSingleStep(0.1)
        self._ampSpin.setFixedWidth(90)
        ctrl_row.addWidget(self._ampSpin)

        ctrl_row.addSpacing(12)

        ctrl_row.addWidget(QLabel("偏移:"))
        self._offsetSpin = QDoubleSpinBox()
        self._offsetSpin.setRange(-1000.0, 1000.0)
        self._offsetSpin.setValue(0.0)
        self._offsetSpin.setDecimals(3)
        self._offsetSpin.setSingleStep(0.1)
        self._offsetSpin.setFixedWidth(90)
        ctrl_row.addWidget(self._offsetSpin)

        ctrl_row.addStretch()
        v_main.addLayout(ctrl_row)

        layout.addWidget(self._vGroup)

        # ── 操作栏 ──
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self._startBtn = QPushButton("Start")
        self._startBtn.setCheckable(True)
        self._startBtn.setFixedWidth(65)
        action_row.addWidget(self._startBtn)

        self._clearBtn = QPushButton("清空")
        self._clearBtn.setFixedWidth(55)
        action_row.addWidget(self._clearBtn)

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
        self._ampSpin.valueChanged.connect(self._onAmpChanged)
        self._offsetSpin.valueChanged.connect(self._onOffsetChanged)
        self._timeWindowSpin.valueChanged.connect(self._onTimeWindowChanged)
        self._scrollbar.valueChanged.connect(self._onScrollChanged)

        # ── Y 范围控制 ──
        self._yAutoCb.toggled.connect(self._onYAutoToggled)
        self._yMinSpin.valueChanged.connect(self._onYRangeChanged)
        self._yMaxSpin.valueChanged.connect(self._onYRangeChanged)

        # ── UI 控件 ──
        self._startBtn.clicked.connect(self._onStartClicked)
        self._clearBtn.clicked.connect(self._onClearClicked)

    # ── 内部计算 ───────────────────────────────────────

    def _calc_visible_count(self) -> int:
        """根据时间窗口和采样间隔计算可见数据点数"""
        if self._sampling_interval_us <= 0 or self._history_rb.count == 0:
            return 0
        count = int(self._time_window_s * 1_000_000 / self._sampling_interval_us)
        return max(1, min(count, self._history_rb.count))

    def _calc_ms_per_div(self, visible_count: int) -> float:
        """计算每格对应多少毫秒"""
        if visible_count <= 0 or self._sampling_interval_us <= 0:
            return 0.0
        total_time_us = visible_count * self._sampling_interval_us
        return total_time_us / 1000.0 / 4.0  # GRID_DIVISIONS = 4

    def _get_scroll_offset(self, total: int, visible_count: int) -> int:
        """将滚动条值转换为 scroll_offset（0=最新）"""
        max_offset = max(0, total - visible_count)
        sb_val = min(self._scrollbar_value, max_offset)
        return max_offset - sb_val

    # ── 渲染 ───────────────────────────────────────────

    def _render_frame(self):
        """从历史 RingBuffer 读取一帧并显示

        NaN 魔法数字（gap 标记）已直接在历史缓冲区中，
        WaveformWidget 检测到 NaN 后绘制红色危险线段。
        """
        vc = self._calc_visible_count()
        if vc <= 0:
            self._waveform.setData([], 0.0)
            return

        total = self._history_rb.count
        scroll_offset = self._get_scroll_offset(total, vc)
        data, _, scrollbar_max, _ = \
            self._history_rb.read_frame(vc, scroll_offset)

        if not data:
            self._waveform.setData([], 0.0)
            return

        # 应用放大倍数和偏移
        if self._amplification != 1.0 or self._offset != 0.0:
            data = [v * self._amplification + self._offset for v in data]

        ms_per_div = self._calc_ms_per_div(len(data))

        # 检查是否在末尾（用于自动跟随）
        at_end = self._scrollbar.value() >= self._scrollbar.maximum()

        # 更新滚动条
        self._scrollbar.blockSignals(True)
        self._scrollbar.setMaximum(scrollbar_max)
        if at_end:
            self._scrollbar.setValue(scrollbar_max)
            self._scrollbar_value = scrollbar_max
        self._scrollbar.blockSignals(False)

        # 更新时间/格显示
        if ms_per_div > 0:
            if ms_per_div < 1:
                self._timePerDivLabel.setText(f"{ms_per_div*1000:.0f}μs/div")
            elif ms_per_div < 1000:
                self._timePerDivLabel.setText(f"{ms_per_div:.1f}ms/div")
            else:
                self._timePerDivLabel.setText(f"{ms_per_div/1000:.2f}s/div")
        else:
            self._timePerDivLabel.setText("---")

        # 发送到波形显示（NaN 魔法数字 gap 标记已在 data 中）
        self._waveform.setData(data, ms_per_div)

    # ── 槽函数 ─────────────────────────────────────────

    @pyqtSlot(list, int, float)
    def _onFrameReady(self, data, _gap_count, sampling_interval_us):
        """收到工作线程的数据 chunk — 直接写入历史缓冲区（含 NaN 魔法数字）

        Args:
            data: float 列表，前 gap_count 个为 NaN 魔法数字（危险区域标记）
            gap_count: 工作线程临时缓冲区丢失的点数
            sampling_interval_us: 采样间隔
        """
        self._sampling_interval_us = sampling_interval_us

        if not data:
            self.renderComplete.emit()
            return

        # 直接写入历史缓冲区（NaN 魔法数字一并写入，渲染时检测处理）
        self._history_rb.write_batch(data)

        # 渲染当前帧
        self._render_frame()

        # 通知工作线程：渲染完成，可发下一帧
        self.renderComplete.emit()

    def _onBufferSizeChanged(self, size: int):
        """调整历史 RingBuffer 大小"""
        self._history_rb.resize(max(100, size))
        self._render_frame()

    def _onAmpChanged(self, value: float):
        """放大倍数改变 → 重绘"""
        self._amplification = value
        self._render_frame()

    def _onOffsetChanged(self, value: float):
        """偏移改变 → 重绘"""
        self._offset = value
        self._render_frame()

    def _onTimeWindowChanged(self, value: float):
        """时间窗口改变 → 重绘"""
        self._time_window_s = max(0.01, value)
        self._render_frame()

    def _onScrollChanged(self, value: int):
        """滚动条改变 → 重绘"""
        self._scrollbar_value = max(0, value)
        self._render_frame()

    def _onYAutoToggled(self, checked):
        self._yMinSpin.setEnabled(not checked)
        self._yMaxSpin.setEnabled(not checked)
        self._onYRangeChanged()

    def _onYRangeChanged(self):
        if self._yAutoCb.isChecked():
            self._waveform.setYRange(auto=True)
        else:
            self._waveform.setYRange(
                self._yMinSpin.value(),
                self._yMaxSpin.value(),
                auto=False,
            )

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
        self._waveform.setData([], 0.0)
        self._clearRequested.emit()

    def cleanup(self):
        """清理工作线程和资源"""
        self._stopRequested.emit()
        self._worker.deleteLater()
        self._thread.quit()
        self._thread.wait(3000)
        self._thread.deleteLater()
