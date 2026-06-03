"""
示波器 UI 和内容部件

包含：
    WaveformWidget      — 自定义波形绘制控件（带时间轴刻度）
    OscilloscopeContent — 内容部件（含工作线程管理）
"""
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
                             QDoubleSpinBox, QPushButton, QWidget,
                             QSizePolicy, QScrollBar)
from PyQt5.QtCore import Qt, QObject, pyqtSignal, pyqtSlot, QMetaObject, QThread
from PyQt5.QtGui import QPainter, QPen, QColor, QPainterPath, QFont

from conn_base import ConnNodeContentWidget
from conn_utils import ThreadManager
from .oscilloscope_core import OscilloscopeSampler


# ═══════════════════════════════════════════════════════════════════════
# 波形绘制控件
# ═══════════════════════════════════════════════════════════════════════

class WaveformWidget(QWidget):
    """自定义波形绘制控件 — 显示数据曲线 + 网格 + 时间轴 + 红色 X 覆盖标记"""

    GRID_LINES = 4  # 水平和垂直网格线数量（5 个区间）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self._overwrite_positions = []
        self._overwrite_count = 0
        self._ms_per_div = 0.0
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def setData(self, data, overwrite_count, overwrite_positions, ms_per_div):
        """设置数据并触发重绘"""
        self._data = data
        self._overwrite_count = overwrite_count
        self._overwrite_positions = overwrite_positions
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
        margin_l = 20
        margin_r = 10
        margin_t = 10
        margin_b = 15
        plot_w = w - margin_l - margin_r
        plot_h = h - margin_t - margin_b

        if plot_w <= 0 or plot_h <= 0:
            painter.end()
            return

        # ── 背景 ──
        painter.fillRect(self.rect(), QColor(0, 0, 0))

        # ── 水平网格线 ──
        painter.setPen(QPen(QColor(30, 30, 30), 1))
        for i in range(self.GRID_LINES + 1):
            y = int(margin_t + plot_h * i / self.GRID_LINES)
            painter.drawLine(margin_l, y, margin_l + plot_w, y)

        # ── 垂直网格线 + 时间标签 ──
        small_font = QFont("monospace", 8)
        painter.setFont(small_font)
        divs = self.GRID_LINES
        for i in range(divs + 1):
            x = int(margin_l + plot_w * i / divs)
            painter.setPen(QPen(QColor(30, 30, 30), 1))
            painter.drawLine(x, margin_t, x, margin_t + plot_h)

            # 底部时间标签
            if self._ms_per_div > 0:
                time_from_now = -(divs - i) * self._ms_per_div
                label = self._format_time_label(time_from_now)
                painter.setPen(QPen(QColor(80, 80, 80), 1))
                text_x = x - 15
                text_y = margin_t + plot_h + 12
                painter.drawText(text_x, text_y, 30, 10,
                                 Qt.AlignCenter, label)

        # ── 右上角显示时间/格 ──
        if self._ms_per_div > 0:
            painter.setPen(QPen(QColor(100, 200, 255), 1))
            text = self._format_ms_per_div(self._ms_per_div)
            painter.drawText(margin_l + 4, margin_t + 4,
                             plot_w - 8, 14,
                             Qt.AlignRight | Qt.AlignTop, text)

        n = len(self._data)
        if n < 2:
            painter.end()
            return

        # ── 计算 Y 轴范围，留 10% 上下余量 ──
        d_min = min(self._data)
        d_max = max(self._data)
        d_range = d_max - d_min
        if d_range < 0.001:
            d_range = 1.0
        d_pad = d_range * 0.1
        d_min -= d_pad
        d_max += d_pad
        d_range = d_max - d_min

        # ── 绘制波形 ──
        path = QPainterPath()
        first = True
        for i, val in enumerate(self._data):
            x = margin_l + (i / (n - 1)) * plot_w
            normalized = (val - d_min) / d_range          # 0~1
            y = margin_t + plot_h * (1.0 - normalized)    # Y 轴翻转
            if first:
                path.moveTo(x, y)
                first = False
            else:
                path.lineTo(x, y)

        painter.setPen(QPen(QColor(0, 220, 0), 2))
        painter.drawPath(path)

        # ── 红色 X 标记（覆盖位置） ──
        if self._overwrite_positions:
            painter.setPen(QPen(QColor(255, 40, 40), 3))
            x_size = 8
            for pos in self._overwrite_positions:
                if 0 <= pos < n:
                    x = int(margin_l + (pos / (n - 1)) * plot_w)
                    y = int(margin_t + plot_h / 2)
                    painter.drawLine(x - x_size, y - x_size,
                                     x + x_size, y + x_size)
                    painter.drawLine(x + x_size, y - x_size,
                                     x - x_size, y + x_size)

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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 波形显示
        self._waveform = WaveformWidget()
        layout.addWidget(self._waveform)

        # 水平滚动条
        self._scrollbar = QScrollBar(Qt.Horizontal)
        self._scrollbar.setMinimum(0)
        self._scrollbar.setMaximum(0)
        self._scrollbar.setValue(0)
        layout.addWidget(self._scrollbar)

        # 控制栏 — 第1行：显示控制 + 操作
        controls1 = QHBoxLayout()
        controls1.setSpacing(6)

        controls1.addWidget(QLabel("FPS:"))
        self._fpsSpin = QSpinBox()
        self._fpsSpin.setRange(1, 120)
        self._fpsSpin.setValue(30)
        self._fpsSpin.setFixedWidth(55)
        controls1.addWidget(self._fpsSpin)

        controls1.addWidget(QLabel("Buffer:"))
        self._bufferSpin = QSpinBox()
        self._bufferSpin.setRange(100, 100000)
        self._bufferSpin.setValue(1000)
        self._bufferSpin.setSingleStep(100)
        self._bufferSpin.setFixedWidth(70)
        controls1.addWidget(self._bufferSpin)

        controls1.addWidget(QLabel("窗口:"))
        self._timeWindowSpin = QDoubleSpinBox()
        self._timeWindowSpin.setRange(0.01, 60.0)
        self._timeWindowSpin.setValue(1.0)
        self._timeWindowSpin.setDecimals(2)
        self._timeWindowSpin.setSingleStep(0.1)
        self._timeWindowSpin.setSuffix(" s")
        self._timeWindowSpin.setFixedWidth(80)
        controls1.addWidget(self._timeWindowSpin)

        self._timePerDivLabel = QLabel("---")
        self._timePerDivLabel.setFixedWidth(90)
        self._timePerDivLabel.setAlignment(Qt.AlignCenter)
        self._timePerDivLabel.setStyleSheet("color: #64c8ff;")
        controls1.addWidget(self._timePerDivLabel)

        controls1.addStretch()

        self._startBtn = QPushButton("Start")
        self._startBtn.setCheckable(True)
        self._startBtn.setFixedWidth(55)
        controls1.addWidget(self._startBtn)

        self._clearBtn = QPushButton("清空")
        self._clearBtn.setFixedWidth(50)
        controls1.addWidget(self._clearBtn)

        self._ovLabel = QLabel("覆盖: 0")
        self._ovLabel.setFixedWidth(70)
        controls1.addWidget(self._ovLabel)

        layout.addLayout(controls1)

        # 控制栏 — 第2行：数据处理
        controls2 = QHBoxLayout()
        controls2.setSpacing(6)

        controls2.addWidget(QLabel("放大:"))
        self._ampSpin = QDoubleSpinBox()
        self._ampSpin.setRange(0.01, 1000.0)
        self._ampSpin.setValue(1.0)
        self._ampSpin.setDecimals(3)
        self._ampSpin.setSingleStep(0.1)
        self._ampSpin.setFixedWidth(80)
        controls2.addWidget(self._ampSpin)

        controls2.addWidget(QLabel("偏移:"))
        self._offsetSpin = QDoubleSpinBox()
        self._offsetSpin.setRange(-1000.0, 1000.0)
        self._offsetSpin.setValue(0.0)
        self._offsetSpin.setDecimals(3)
        self._offsetSpin.setSingleStep(0.1)
        self._offsetSpin.setFixedWidth(80)
        controls2.addWidget(self._offsetSpin)

        controls2.addStretch()
        layout.addLayout(controls2)

        # ── 样式 ──
        self.setStyleSheet("""
            OscilloscopeContent {
                background-color: #000000;
            }
            QSpinBox, QDoubleSpinBox, QPushButton, QLabel {
                background-color: #202020;
                color: #e0e0e0;
                border: 1px solid #404040;
                padding: 2px 4px;
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

        # ── 信号连接 ──
        self._connectSignals()

        # 默认大小（稍宽以容纳新控件）
        self.resize(480, 260)

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

        # ── UI 控件 ──
        self._startBtn.clicked.connect(self._onStartClicked)

    # ── 槽函数 ──

    def _onFrameReady(self, data, overwrite_count, overwrite_positions,
                      ms_per_div, scrollbar_max):
        """收到一帧数据：更新波形 + 滚动条 + 时间/格显示 → 通知下一帧"""
        self._waveform.setData(data, overwrite_count,
                                overwrite_positions, ms_per_div)

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
        self._waveform.setData([], 0, [], 0.0)
        self._clearRequested.emit()

    def cleanup(self):
        """清理工作线程和资源"""
        self._stopRequested.emit()
        self._worker.deleteLater()
        self._thread.quit()
        self._thread.wait(3000)
        self._thread.deleteLater()
