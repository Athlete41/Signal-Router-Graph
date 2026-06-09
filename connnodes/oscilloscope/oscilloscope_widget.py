"""
示波器 UI 和内容部件

包含：
    WaveformWidget          — 自定义波形绘制控件（带时间轴刻度）
    OscilloscopeContent     — 内容部件（含工作线程管理）
"""
import math
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel,
                             QSpinBox, QDoubleSpinBox, QPushButton, QWidget,
                             QSizePolicy, QScrollBar, QGroupBox, QCheckBox)
from PyQt5.QtCore import Qt, QObject, pyqtSignal, pyqtSlot, QMetaObject, QThread
from PyQt5.QtGui import QPainter, QPen, QColor, QPainterPath, QFont

from conn_base import ConnNodeContentWidget
from conn_utils import ThreadManager
from .oscilloscope_core import OscilloscopeSampler


# ═══════════════════════════════════════════════════════════════════════
# 波形绘制控件
# ═══════════════════════════════════════════════════════════════════════

class WaveformWidget(QWidget):
    """自定义波形绘制控件 — 显示数据曲线 + 网格 + 时间轴 + 覆盖标记"""

    GRID_LINES = 4  # 水平和垂直网格线数量（5 个区间）

    @staticmethod
    def _nice_bounds(d_min: float, d_max: float, divisions: int = 4):
        """计算覆盖数据范围的人类友好型坐标轴范围

        保证步长是 1/2/5 × 10^k，而不是 0.6、0.7 这类非整数。

        Returns:
            (nice_min, nice_max, nice_step)
        """
        raw_range = d_max - d_min
        if raw_range < 0.0001:
            return -0.5, 0.5, 0.25

        # 原始步长
        raw_step = raw_range / divisions
        exponent = math.floor(math.log10(raw_step))
        mantissa = raw_step / (10 ** exponent)

        # 吸附到 1/2/5
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

        # 保证至少有 divisions 个区间
        if (nice_max - nice_min) / nice_step < divisions:
            nice_max = nice_min + nice_step * divisions

        return nice_min, nice_max, nice_step

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self._overwrite_region = ()          # () 或 (min_idx, max_idx) 在 data 中的索引
        self._overwrite_count = 0
        self._ms_per_div = 0.0
        # Y 范围控制（None = 自动）
        self._y_auto = True
        self._y_min = None
        self._y_max = None
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def setYRange(self, y_min=None, y_max=None, auto=True):
        """设置 Y 轴显示范围

        Args:
            y_min: 下限（None 时自动）
            y_max: 上限（None 时自动）
            auto: True = 自动计算并吸附到友好值
        """
        self._y_auto = auto
        if not auto:
            self._y_min = y_min if y_min is not None else -5.0
            self._y_max = y_max if y_max is not None else 5.0
        else:
            self._y_min = None
            self._y_max = None
        self.update()

    def setData(self, data, overwrite_count, overwrite_region, ms_per_div):
        """设置数据并触发重绘

        Args:
            data: 浮点数列表
            overwrite_count: 总覆盖次数
            overwrite_region: () 或 (min, max) — data 切片内的覆盖区域边界
            ms_per_div: 每格毫秒数
        """
        self._data = data
        self._overwrite_count = overwrite_count
        self._overwrite_region = overwrite_region
        self._ms_per_div = ms_per_div
        self.update()

    def _format_time_label(self, ms: float) -> str:
        """将毫秒值格式化为可读的时间标签"""
        if abs(ms) < 1:
            return f"{ms * 1000:.0f}μs"
        elif abs(ms) < 1000:
            return f"{ms:.0f}ms"
        else:
            return f"{ms / 1000:.2f}s"

    def _format_ms_per_div(self, ms_per_div: float) -> str:
        """格式化每格时间显示"""
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
        margin_l = 52          # 左侧留空给 Y 轴标签
        margin_r = 10
        margin_t = 10
        margin_b = 24          # 底部留空给时间标签
        plot_w = w - margin_l - margin_r
        plot_h = h - margin_t - margin_b

        if plot_w <= 0 or plot_h <= 0:
            painter.end()
            return

        # ── 背景 ──
        painter.fillRect(self.rect(), QColor(0, 0, 0))

        # ── 计算 Y 轴范围（先算，后面网格和标签都要用） ──
        n = len(self._data)
        if n >= 2 and self._y_auto:
            d_min = min(self._data)
            d_max = max(self._data)
            # 自动模式：吸附到友好数值
            y_min, y_max, y_step = self._nice_bounds(d_min, d_max, self.GRID_LINES)
        elif n >= 2 and not self._y_auto:
            y_min = self._y_min
            y_max = self._y_max
            if y_max <= y_min:
                y_min, y_max = -5.0, 5.0
            y_step = (y_max - y_min) / self.GRID_LINES
        else:
            y_min = -1.0
            y_max = 1.0
            y_step = 0.5
        d_range = y_max - y_min

        # ── 水平网格线 + Y 轴标签 ──
        small_font = QFont("monospace", 8)
        painter.setFont(small_font)
        for i in range(self.GRID_LINES + 1):
            y = int(margin_t + plot_h * i / self.GRID_LINES)
            painter.setPen(QPen(QColor(60, 60, 60), 1))
            painter.drawLine(margin_l, y, margin_l + plot_w, y)

            # 左侧 Y 轴数值标签
            if d_range > 0:
                normalized = 1.0 - i / self.GRID_LINES   # 顶部=1, 底部=0
                value = y_min + normalized * d_range
                # 根据数值大小自适应格式化
                if abs(value) < 0.0001:
                    label = "0"
                elif abs(value) < 0.01:
                    label = f"{value:.2e}"
                elif abs(value) < 100:
                    label = f"{value:.3f}"
                else:
                    label = f"{value:.1f}"
                painter.setPen(QPen(QColor(180, 180, 180), 1))
                painter.drawText(2, y - 6, margin_l - 6, 12,
                                 Qt.AlignRight | Qt.AlignVCenter, label)

        # ── 垂直网格线 + X 轴时间标签 ──
        divs = self.GRID_LINES
        for i in range(divs + 1):
            x = int(margin_l + plot_w * i / divs)
            painter.setPen(QPen(QColor(60, 60, 60), 1))
            painter.drawLine(x, margin_t, x, margin_t + plot_h)

            # 底部时间标签
            if self._ms_per_div > 0:
                time_from_now = -(divs - i) * self._ms_per_div
                label = self._format_time_label(time_from_now)
                painter.setPen(QPen(QColor(180, 180, 180), 1))
                text_w = 42
                text_x = x - text_w // 2
                text_y = margin_t + plot_h + 4
                painter.drawText(text_x, text_y, text_w, 16,
                                 Qt.AlignCenter, label)

        # ── 右上角状态信息 ──
        info_y = margin_t + 2
        if self._ms_per_div > 0:
            painter.setPen(QPen(QColor(100, 200, 255), 1))
            text = self._format_ms_per_div(self._ms_per_div)
            painter.drawText(margin_l + 4, info_y,
                             plot_w - 8, 14,
                             Qt.AlignRight | Qt.AlignTop, text)
            info_y += 16

        # 显示幅值/格
        if d_range > 0:
            v_per_div = d_range / self.GRID_LINES
            painter.setPen(QPen(QColor(240, 192, 64), 1))
            text = f"{v_per_div:.4g}V/div"
            painter.drawText(margin_l + 4, info_y,
                             plot_w - 8, 14,
                             Qt.AlignRight | Qt.AlignTop, text)

        # ── 绘制波形 ──
        if n >= 2:
            path = QPainterPath()
            first = True
            for i, val in enumerate(self._data):
                x = margin_l + (i / (n - 1)) * plot_w
                normalized = (val - y_min) / d_range          # 0~1
                y = margin_t + plot_h * (1.0 - normalized)    # Y 轴翻转
                if first:
                    path.moveTo(x, y)
                    first = False
                else:
                    path.lineTo(x, y)

            painter.setPen(QPen(QColor(0, 220, 0), 2))
            painter.drawPath(path)

            # ── 红色垂直线标记（缓冲区覆盖导致的不可信任区域边界） ──
            if self._overwrite_region:
                ov_min, ov_max = self._overwrite_region
                painter.setPen(QPen(QColor(255, 50, 50), 3))
                for boundary in (ov_min, ov_max):
                    if 0 <= boundary < n:
                        x = int(margin_l + (boundary / (n - 1)) * plot_w)
                        painter.drawLine(x, margin_t, x, margin_t + plot_h)

        painter.end()


# ═══════════════════════════════════════════════════════════════════════
# 示波器内容部件
# ═══════════════════════════════════════════════════════════════════════

class OscilloscopeContent(ConnNodeContentWidget):
    """
    示波器内容部件 — 管理工作线程、UI、渲染握手

    信号：
        renderComplete — 通知工作线程当前帧已渲染完成
    """
    renderComplete = pyqtSignal()
    _startRequested = pyqtSignal()
    _stopRequested = pyqtSignal()
    _clearRequested = pyqtSignal()

    class _Worker(QObject):
        """工作线程辅助对象，负责在工作线程中创建 OscilloscopeSampler"""

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
        self._bufferSpin.setRange(100, 100000)
        self._bufferSpin.setValue(10000)
        self._bufferSpin.setSingleStep(100)
        self._bufferSpin.setFixedWidth(75)
        acq_grid.addWidget(self._bufferSpin)

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
        self._timePerDivLabel.setStyleSheet("color: #64c8ff; border: none; font-size: 12px; font-weight: bold;")
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

        self._ovLabel = QLabel("覆盖: 0")
        self._ovLabel.setFixedWidth(100)
        self._ovLabel.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._ovLabel.setStyleSheet("border: none;")
        action_row.addWidget(self._ovLabel)

        layout.addLayout(action_row)

        # ── 整体样式 ──
        self._applyStyleSheet()

        # ── 信号连接 ──
        self._connectSignals()

        # 默认大小
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
            /* 采集系统 — 蓝色调 */
            #acqGroup {
                border-color: #2a6a9a;
            }
            #acqGroup::title {
                color: #5aadff;
            }
            /* 水平系统 — 青色调 */
            #hGroup {
                border-color: #2a7a7a;
            }
            #hGroup::title {
                color: #4adcdc;
            }
            /* 垂直系统 — 暖色调 */
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
                width: 8px;
                height: 8px;
            }
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
                width: 8px;
                height: 8px;
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
        """连接所有信号（UI + 跨线程握手）"""
        # ── 渲染握手 ──
        self.sampler.frameReady.connect(self._onFrameReady)
        self.renderComplete.connect(self.sampler.onRenderComplete)

        # ── 控制桥接（跨线程） ──
        self._startRequested.connect(self.sampler.start)
        self._stopRequested.connect(self.sampler.stop)
        self._fpsSpin.valueChanged.connect(self.sampler.setFps)
        self._bufferSpin.valueChanged.connect(self.sampler.setBufferSize)
        self._ampSpin.valueChanged.connect(self.sampler.setAmplification)
        self._offsetSpin.valueChanged.connect(self.sampler.setOffset)
        self._timeWindowSpin.valueChanged.connect(self.sampler.setTimeWindow)
        self._scrollbar.valueChanged.connect(self.sampler.setScrollPos)
        self._clearRequested.connect(self.sampler.clear)
        self._clearBtn.clicked.connect(self._onClearClicked)

        # ── Y 范围控制 ──
        self._yAutoCb.toggled.connect(self._onYAutoToggled)
        self._yMinSpin.valueChanged.connect(self._onYRangeChanged)
        self._yMaxSpin.valueChanged.connect(self._onYRangeChanged)

        # ── UI 控件 ──
        self._startBtn.clicked.connect(self._onStartClicked)

    # ── 槽函数 ──

    def _onYAutoToggled(self, checked):
        """自动 Y 范围切换：禁用/启用 Y 下限/上限 SpinBox"""
        self._yMinSpin.setEnabled(not checked)
        self._yMaxSpin.setEnabled(not checked)
        self._onYRangeChanged()

    def _onYRangeChanged(self):
        """手动 Y 范围变更 → 更新波形"""
        if self._yAutoCb.isChecked():
            self._waveform.setYRange(auto=True)
        else:
            self._waveform.setYRange(
                self._yMinSpin.value(),
                self._yMaxSpin.value(),
                auto=False,
            )

    def _onFrameReady(self, data, overwrite_count, overwrite_region,
                      ms_per_div, scrollbar_max):
        """收到一帧数据：更新波形 + 滚动条 + 时间/格显示 → 通知下一帧"""
        # 同步 Y 范围（新帧数据可能更新自动范围）
        if self._yAutoCb.isChecked():
            self._waveform.setYRange(auto=True)
        else:
            self._waveform.setYRange(
                self._yMinSpin.value(),
                self._yMaxSpin.value(),
                auto=False,
            )
        self._waveform.setData(data, overwrite_count,
                                overwrite_region, ms_per_div)

        # 更新时间/格静态显示
        if ms_per_div > 0:
            if ms_per_div < 1:
                self._timePerDivLabel.setText(f"{ms_per_div*1000:.0f}μs/div")
            elif ms_per_div < 1000:
                self._timePerDivLabel.setText(f"{ms_per_div:.1f}ms/div")
            else:
                self._timePerDivLabel.setText(f"{ms_per_div/1000:.2f}s/div")
        else:
            self._timePerDivLabel.setText("---")

        # 更新覆盖计数
        self._ovLabel.setText(f"覆盖: {overwrite_count}")

        # 更新滚动条范围（保持最新位置标记）
        was_at_end = self._scrollbar.value() >= self._scrollbar.maximum()
        self._scrollbar.blockSignals(True)
        self._scrollbar.setMaximum(scrollbar_max)
        if was_at_end:
            self._scrollbar.setValue(scrollbar_max)
        self._scrollbar.blockSignals(False)
        # 同步 sampler 的 _scrollbar_value（blockSignals 期间信号未发出，sampler 不知情）
        self._scrollbar.valueChanged.emit(self._scrollbar.value())

        # 强制同步渲染
        self._waveform.repaint()
        self.renderComplete.emit()

    def _onStartClicked(self, checked):
        """启动/停止工作线程的帧定时器"""
        if checked:
            self._startRequested.emit()
            self._startBtn.setText("Stop")
        else:
            self._stopRequested.emit()
            self._startBtn.setText("Start")

    def _onClearClicked(self):
        """清空显示和缓存（通过桥接信号跨线程安全调用）"""
        self._waveform.setData([], 0, (), 0.0)
        self._clearRequested.emit()

    def cleanup(self):
        """清理工作线程和资源"""
        self._stopRequested.emit()
        self._worker.deleteLater()
        self._thread.quit()
        self._thread.wait(3000)
        self._thread.deleteLater()
