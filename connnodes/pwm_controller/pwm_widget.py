"""
PWM 控制器 — 内容部件

PwmControllerWidget (ConnNodeContentWidget)
  ├── 静态 UI: 操作栏 + 起始通道 + 4 路通道 GroupBox + 状态标签
  ├── 嵌套 _Worker(QObject) 持有 _PwmCore（工作线程）
  ├── 4 个 per-channel 输出信号 + 4 个 per-channel dict 输入槽
  └── 定时 fetch QTimer (主线程)
"""

from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QCheckBox, QSpinBox, QDoubleSpinBox, QSlider,
    QFrame,
)
from PyQt5.QtCore import (
    Qt, QThread, QObject, pyqtSignal, pyqtSlot,
    QMetaObject, QTimer, QByteArray,
)

from .pwm_core import _PwmCore
from .pwm_protocol import PwmChannelInfo
from conn_utils import easyError, easyWarning, easyDebug, ThreadManager
from conn_base import ConnNodeContentWidget


class PwmControllerWidget(ConnNodeContentWidget):
    """PWM 控制器内容部件（主线程）"""

    # ── Per-channel 输出信号 ────────────────────────────────

    ch1Send = pyqtSignal(QByteArray)
    ch2Send = pyqtSignal(QByteArray)
    ch3Send = pyqtSignal(QByteArray)
    ch4Send = pyqtSignal(QByteArray)

    CHANNEL_COUNT = 4
    """固定 4 路本地 PWM 通道"""

    # ── _Worker（持有 _PwmCore）────────────────────────────

    class _Worker(QObject):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._isInit = False
            self._core: _PwmCore = None

        @pyqtSlot()
        def initCore(self):
            if not self._isInit:
                self._isInit = True
                self._core = _PwmCore(self)

    # ── initUI / cleanup ────────────────────────────────────

    def initUI(self):
        # 1. 工作线程
        self._worker = self.__class__._Worker()
        self._thread = QThread()
        self._thread.start()
        ThreadManager.instance().register_thread(self._thread)

        self._worker.moveToThread(self._thread)
        QMetaObject.invokeMethod(self._worker, "initCore", Qt.BlockingQueuedConnection)
        self._core: _PwmCore = self._worker._core

        # 2. 起始通道偏移
        self._baseChannel = 0

        # 3. Per-channel 状态追踪
        self._ch_output_connected: list[bool] = [False] * self.CHANNEL_COUNT
        self._last_channel_states: list = [None] * self.CHANNEL_COUNT  # PwmChannelInfo or None

        # 4. 自动刷新定时器（主线程）
        self._autoFetchTimer = QTimer(self)
        self._autoFetchTimer.timeout.connect(self._core.fetchPwmInfo)

        # 5. 构建 UI
        self._buildUI()

        # 6. 连接信号
        self._connectSignals()

        # 7. 初始状态
        self._updateAllConnectionStates(False)

    def cleanup(self):
        """清理工作线程"""
        if hasattr(self, '_autoFetchTimer'):
            self._autoFetchTimer.stop()

        if hasattr(self, '_core'):
            QMetaObject.invokeMethod(self._core, "shutdown", Qt.BlockingQueuedConnection)

        if hasattr(self, '_worker'):
            self._worker.deleteLater()

        if hasattr(self, '_thread'):
            self._thread.quit()
            self._thread.wait(3000)
            self._thread.deleteLater()

    # ── 通道索引转换 ───────────────────────────────────────

    def _mcuToLocal(self, mcu_ch_idx: int) -> int:
        """MCU 通道索引 → 本地通道索引（0-3），不在范围内返回 -1"""
        local = mcu_ch_idx - self._baseChannel
        return local if 0 <= local < self.CHANNEL_COUNT else -1

    def _localToMcu(self, local_idx: int) -> int:
        """本地通道索引 → MCU 通道索引"""
        return self._baseChannel + local_idx

    # ── UI 构建 ─────────────────────────────────────────────

    def _buildUI(self):
        self.resize(320, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(4)

        # ── 操作栏 ──
        op_row = QHBoxLayout()
        op_row.setSpacing(6)

        self._fetchBtn = QPushButton("获取PWM信息")
        self._fetchBtn.setFixedHeight(26)
        self._fetchBtn.clicked.connect(self._onFetchClicked)
        op_row.addWidget(self._fetchBtn)

        self._autoRefreshCheck = QCheckBox("定时刷新")
        self._autoRefreshCheck.toggled.connect(self._onAutoRefreshToggled)
        op_row.addWidget(self._autoRefreshCheck)

        self._intervalSpin = QSpinBox()
        self._intervalSpin.setRange(100, 10000)
        self._intervalSpin.setSingleStep(100)
        self._intervalSpin.setValue(1000)
        self._intervalSpin.setSuffix("ms")
        self._intervalSpin.setFixedWidth(90)
        self._intervalSpin.valueChanged.connect(self._onIntervalChanged)
        op_row.addWidget(self._intervalSpin)

        op_row.addStretch()
        root.addLayout(op_row)

        # ── 起始通道 ──
        base_row = QHBoxLayout()
        base_row.setSpacing(4)
        base_row.addWidget(QLabel("起始通道:"))
        self._baseSpin = QSpinBox()
        self._baseSpin.setRange(0, 252)
        self._baseSpin.setSingleStep(4)
        self._baseSpin.setValue(0)
        self._baseSpin.setFixedWidth(70)
        self._baseSpin.setToolTip("MCU 起始通道索引: 0 → 控通道 0~3 (显示 1~4)\n4 → 控通道 4~7 (显示 5~8)")
        self._baseSpin.valueChanged.connect(self._onBaseChannelChanged)
        base_row.addWidget(self._baseSpin)

        self._baseHintLabel = QLabel("→ 通道 1~4")
        self._baseHintLabel.setStyleSheet("color: #888;")
        base_row.addWidget(self._baseHintLabel)
        base_row.addStretch()
        root.addLayout(base_row)

        # ── 分隔线 ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet("QFrame { color: #404040; }")
        root.addWidget(sep)

        # ── 4 路通道 GroupBox（直接排列，无 QScrollArea）───
        self._ch_groups: list[QGroupBox] = []
        self._ch_freq_spins: list[QSpinBox] = []
        self._ch_duty_sliders: list[QSlider] = []
        self._ch_duty_spins: list[QDoubleSpinBox] = []
        self._ch_enable_checks: list[QCheckBox] = []

        for i in range(self.CHANNEL_COUNT):
            grp, freq_spin, duty_slider, duty_spin, enable_check = self._createChannelGroup(i)
            self._ch_groups.append(grp)
            self._ch_freq_spins.append(freq_spin)
            self._ch_duty_sliders.append(duty_slider)
            self._ch_duty_spins.append(duty_spin)
            self._ch_enable_checks.append(enable_check)
            root.addWidget(grp)

        root.addStretch()

        # ── 状态标签（底部）──
        self._statusLabel = QLabel("就绪 — 点击「获取PWM信息」查询 MCU")
        self._statusLabel.setWordWrap(True)
        self._statusLabel.setStyleSheet("color: #888; font-size: 11px; padding: 2px;")
        root.addWidget(self._statusLabel)

        # ── 应用样式 ──
        self._applyStyleSheet()

    def _createChannelGroup(self, idx: int) -> tuple:
        """为单个通道创建 QGroupBox 及内部控件（2行紧凑布局）"""
        grp = QGroupBox(f"通道 {idx + 1}")
        grp.setObjectName(f"chGroup{idx}")

        layout = QVBoxLayout(grp)
        layout.setContentsMargins(8, 12, 8, 6)
        layout.setSpacing(2)

        # 行1: 频率 + 占空比
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        row1.addWidget(QLabel("频率:"))
        freq_spin = QSpinBox()
        freq_spin.setRange(0, 999999)
        freq_spin.setSuffix(" Hz")
        freq_spin.setFixedWidth(100)
        freq_spin.setEnabled(False)
        row1.addWidget(freq_spin)

        row1.addWidget(QLabel("占空比:"))
        duty_slider = QSlider(Qt.Horizontal)
        duty_slider.setRange(0, 10000)
        duty_slider.setEnabled(False)
        duty_slider.setFixedWidth(80)
        row1.addWidget(duty_slider)

        duty_spin = QDoubleSpinBox()
        duty_spin.setRange(0.0, 100.0)
        duty_spin.setDecimals(2)
        duty_spin.setSuffix("%")
        duty_spin.setFixedWidth(80)
        duty_spin.setEnabled(False)
        row1.addWidget(duty_spin)

        row1.addStretch()
        layout.addLayout(row1)

        # 行2: 启用
        row2 = QHBoxLayout()
        row2.setSpacing(4)
        enable_check = QCheckBox("启用")
        enable_check.setEnabled(False)
        row2.addWidget(enable_check)
        row2.addStretch()
        layout.addLayout(row2)

        return grp, freq_spin, duty_slider, duty_spin, enable_check

    def _applyStyleSheet(self):
        """应用暗色主题样式（与 oscilloscope/signal_generator 一致）"""
        self.setStyleSheet("""
            PwmControllerWidget {
                background-color: #0a0a0a;
            }
            QGroupBox {
                font-size: 11px;
                font-weight: bold;
                color: #e0e0e0;
                border: 1px solid #404040;
                border-radius: 4px;
                margin-top: 6px;
                padding: 10px 4px 4px 4px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                color: #c0c0c0;
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
                width: 16px;
                background-color: #353535;
                border: 1px solid #505050;
                border-left: none;
                border-bottom: none;
                border-top-right-radius: 3px;
            }
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 16px;
                background-color: #353535;
                border: 1px solid #505050;
                border-left: none;
                border-top: none;
                border-bottom-right-radius: 3px;
            }
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
                width: 0; height: 0;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 5px solid white;
            }
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
                width: 0; height: 0;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid white;
            }
            QSlider::groove:horizontal {
                background: #353535;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #5aadff;
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: #2a6a9a;
                border-radius: 3px;
            }
            QCheckBox {
                color: #c0c0c0;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #505050;
                border-radius: 3px;
                background-color: #202020;
            }
            QCheckBox::indicator:checked {
                background-color: #2a6a9a;
                border-color: #5aadff;
            }
            QPushButton {
                background-color: #353535;
                color: #e0e0e0;
                border: 1px solid #505050;
                padding: 4px 10px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #454545;
                border-color: #5aadff;
            }
            QPushButton:disabled {
                color: #666;
                background-color: #2a2a2a;
            }
            QLabel {
                color: #e0e0e0;
                background: transparent;
            }
        """)

    # ── 信号连接 ────────────────────────────────────────────

    def _connectSignals(self):
        """连接 Widget ↔ Core 的所有信号"""
        # Core → Widget（跨线程，AutoConnection 自动投递）
        self._core.commandForChannel.connect(self._onCommandForChannel)
        self._core.commandBroadcast.connect(self._onCommandBroadcast)
        self._core.pwmInfoReady.connect(self._onInfoReceived)
        self._core.setAckReady.connect(self._onAckReceived)
        self._core.errorReceived.connect(self._onErrorReceived)

        # 4 路控件 → Core (跨线程)
        for i in range(self.CHANNEL_COUNT):
            self._ch_freq_spins[i].valueChanged.connect(
                lambda val, ch=i: self._onChannelFreqChanged(ch, val))
            self._ch_duty_sliders[i].valueChanged.connect(
                lambda val, ch=i: self._onChannelDutySliderChanged(ch, val))
            self._ch_duty_spins[i].valueChanged.connect(
                lambda val, ch=i: self._onChannelDutySpinChanged(ch, val))
            self._ch_enable_checks[i].toggled.connect(
                lambda checked, ch=i: self._onChannelEnableToggled(ch, checked))

    # ── 公共接口 ────────────────────────────────────────────

    def setChOutputConnected(self, local_idx: int, connected: bool):
        """单路输出端口连接状态变更（由 Node.onEdgeConnectionChanged 调用）

        当某通道的输出端口有边连接时，启用该通道的 UI 控件；断开时禁用。
        fetchBtn 的启用状态由 Node._updateFetchButtonState 控制。
        """
        if 0 <= local_idx < self.CHANNEL_COUNT:
            self._ch_output_connected[local_idx] = connected
            self._applyChannelEnableState(local_idx)

    def _applyChannelEnableState(self, local_idx: int):
        """根据 fetch 数据 + 输出连接状态，决定通道控件的最终启用状态"""
        ch_info = self._last_channel_states[local_idx]
        has_output = self._ch_output_connected[local_idx]

        if ch_info is None:
            # 还没 fetch 过，禁用所有
            self._ch_freq_spins[local_idx].setEnabled(False)
            self._ch_duty_sliders[local_idx].setEnabled(False)
            self._ch_duty_spins[local_idx].setEnabled(False)
            self._ch_enable_checks[local_idx].setEnabled(False)
            return

        # 有 fetch 数据 + 有输出连接 → 根据 occupied/adjustable 决定
        self._ch_freq_spins[local_idx].setEnabled(
            has_output and ch_info.occupied and ch_info.freq_adjustable)
        self._ch_duty_sliders[local_idx].setEnabled(
            has_output and ch_info.occupied and ch_info.duty_adjustable)
        self._ch_duty_spins[local_idx].setEnabled(
            has_output and ch_info.occupied and ch_info.duty_adjustable)
        self._ch_enable_checks[local_idx].setEnabled(
            has_output and ch_info.occupied)

    def restoreFromSerializedData(self, channels_data: list):
        """从序列化数据恢复 UI（不发送命令）"""
        for i, ch_dict in enumerate(channels_data):
            if i >= self.CHANNEL_COUNT:
                break
            ch = PwmChannelInfo.from_dict(ch_dict)
            self._applyChannelState(i, ch)

    def getChannelsData(self) -> list:
        """获取当前 UI 显示的通道数据（用于序列化）"""
        result = []
        for i in range(self.CHANNEL_COUNT):
            info = PwmChannelInfo(
                index=i,
                name=str(self._baseChannel + i + 1),
                freq_current=self._ch_freq_spins[i].value(),
                duty_current=int(self._ch_duty_spins[i].value() * 100),
                enabled=self._ch_enable_checks[i].isChecked(),
            )
            info.freq_min = self._ch_freq_spins[i].minimum()
            info.freq_max = self._ch_freq_spins[i].maximum()
            info.duty_min = int(self._ch_duty_spins[i].minimum() * 100)
            info.duty_max = int(self._ch_duty_spins[i].maximum() * 100)
            result.append(info.to_dict())
        return result

    # ── Per-channel 自动控制入口 ────────────────────────────

    @pyqtSlot(dict)
    def handleCh1Ctrl(self, cmd: dict):
        self._handleChannelCtrl(0, cmd)

    @pyqtSlot(dict)
    def handleCh2Ctrl(self, cmd: dict):
        self._handleChannelCtrl(1, cmd)

    @pyqtSlot(dict)
    def handleCh3Ctrl(self, cmd: dict):
        self._handleChannelCtrl(2, cmd)

    @pyqtSlot(dict)
    def handleCh4Ctrl(self, cmd: dict):
        self._handleChannelCtrl(3, cmd)

    def _handleChannelCtrl(self, local_idx: int, cmd: dict):
        """统一处理 per-channel 自动控制（不更新 UI）

        local_idx: 本地通道索引 0-3，实际 MCU 通道 = base + local_idx
        """
        if not isinstance(cmd, dict):
            easyWarning(f"[PWM] ch{local_idx+1}_ctrl 收到非 dict 类型数据，已忽略")
            return

        if cmd.get("cmd") == "fetch":
            easyDebug(f"[PWM] ch{local_idx+1}_ctrl 触发 fetch")
            self._core.fetchPwmInfo()
            return

        mcu_ch = self._localToMcu(local_idx)

        if "freq" in cmd:
            freq = cmd["freq"]
            if isinstance(freq, (int, float)) and freq > 0:
                self._core.setFreq(mcu_ch, int(freq))
            else:
                easyWarning(f"[PWM] ch{local_idx+1}_ctrl freq={freq} 无效，已忽略")

        if "duty" in cmd:
            duty_pct = cmd["duty"]
            if isinstance(duty_pct, (int, float)) and 0 <= duty_pct <= 100:
                self._core.setDuty(mcu_ch, int(duty_pct * 100))
            else:
                easyWarning(f"[PWM] ch{local_idx+1}_ctrl duty={duty_pct} 无效 (需 0-100)")

        if "enable" in cmd:
            enable = cmd["enable"]
            if isinstance(enable, bool):
                self._core.setEnable(mcu_ch, enable)
            else:
                easyWarning(f"[PWM] ch{local_idx+1}_ctrl enable={enable} 无效 (需 bool)")

    # ── UI 事件处理 ─────────────────────────────────────────

    def _onFetchClicked(self):
        """用户点击获取按钮"""
        self._statusLabel.setText("正在查询 PWM 信息...")
        self._statusLabel.setStyleSheet("color: #cc0; font-size: 11px; padding: 2px;")
        self._core.fetchPwmInfo()

    def _onAutoRefreshToggled(self, checked: bool):
        """定时刷新开关"""
        if checked:
            interval = self._intervalSpin.value()
            self._autoFetchTimer.start(interval)
            self._statusLabel.setText(f"定时刷新中（间隔 {interval} ms）...")
            self._statusLabel.setStyleSheet("color: #0a0; font-size: 11px; padding: 2px;")
        else:
            self._autoFetchTimer.stop()
            self._statusLabel.setText("定时刷新已停止")
            self._statusLabel.setStyleSheet("color: #888; font-size: 11px; padding: 2px;")

    def _onIntervalChanged(self, val: int):
        """刷新间隔改变"""
        if self._autoFetchTimer.isActive():
            self._autoFetchTimer.setInterval(val)
            self._statusLabel.setText(f"定时刷新中（间隔 {val} ms）...")

    def _onBaseChannelChanged(self, base: int):
        """起始通道偏移改变 → 更新 UI 标题和提示"""
        self._baseChannel = base
        for i in range(self.CHANNEL_COUNT):
            mcu_ch = base + i
            self._ch_groups[i].setTitle(f"通道 {mcu_ch + 1}")
        self._baseHintLabel.setText(f"→ 通道 {base+1}~{base+4}")
        # 不发送命令，等用户手动 fetch

    def _onChannelFreqChanged(self, local_idx: int, freq_hz: int):
        """用户调节频率 spinbox"""
        self._core.setFreq(self._localToMcu(local_idx), freq_hz)

    def _onChannelDutySliderChanged(self, local_idx: int, slider_val: int):
        """用户拖动占空比滑块 → 同步 spinbox → 发送命令"""
        spin = self._ch_duty_spins[local_idx]
        spin.blockSignals(True)
        spin.setValue(slider_val / 100.0)
        spin.blockSignals(False)
        self._core.setDuty(self._localToMcu(local_idx), slider_val)

    def _onChannelDutySpinChanged(self, local_idx: int, pct_val: float):
        """用户修改占空比数字框 → 同步 slider → 发送命令"""
        slider = self._ch_duty_sliders[local_idx]
        raw = int(pct_val * 100)
        slider.blockSignals(True)
        slider.setValue(raw)
        slider.blockSignals(False)
        self._core.setDuty(self._localToMcu(local_idx), raw)

    def _onChannelEnableToggled(self, local_idx: int, checked: bool):
        """用户切换启用复选框"""
        self._core.setEnable(self._localToMcu(local_idx), checked)

    # ── Core 回调处理 ───────────────────────────────────────

    @pyqtSlot(int, QByteArray)
    def _onCommandForChannel(self, mcu_ch_idx: int, packet: QByteArray):
        """Core 准备好通道专用协议包 → 路由到对应输出端口"""
        local = self._mcuToLocal(mcu_ch_idx)
        if local < 0:
            return  # 不在本节点管理范围
        signals = [self.ch1Send, self.ch2Send, self.ch3Send, self.ch4Send]
        signals[local].emit(packet)

    @pyqtSlot(QByteArray)
    def _onCommandBroadcast(self, packet: QByteArray):
        """Core 广播命令（FETCH） → 所有 4 路输出端口"""
        for sig in [self.ch1Send, self.ch2Send, self.ch3Send, self.ch4Send]:
            sig.emit(packet)

    @pyqtSlot(list)
    def _onInfoReceived(self, channels: list):
        """收到 fetch 响应 → 更新所有通道 UI"""
        self._statusLabel.setText(f"已获取 {len(channels)} 个 PWM 通道")
        self._statusLabel.setStyleSheet("color: #0a0; font-size: 11px; padding: 2px;")

        for i, ch in enumerate(channels):
            if i >= self.CHANNEL_COUNT:
                break
            self._applyChannelState(i, ch)

    @pyqtSlot(int, int, object)
    def _onAckReceived(self, ch_idx: int, cmd: int, value):
        """MCU 确认 SET 命令"""
        easyDebug(f"[PWM] ACK: MCU通道{ch_idx} 命令0x{cmd:02X} = {value}")

    @pyqtSlot(int, int)
    def _onErrorReceived(self, err_code: int, ch_idx: int):
        """接收到错误"""
        from .pwm_protocol import get_error_message

        if err_code == 0xFE:
            msg = "超时 — 请检查串口连接"
        else:
            ch_name = f"MCU通道{ch_idx}" if ch_idx >= 0 else "?"
            msg = f"MCU 错误: {get_error_message(err_code)} ({ch_name})"

        self._statusLabel.setText(msg)
        self._statusLabel.setStyleSheet("color: #e44; font-size: 11px; padding: 2px;")
        easyError(f"[PWM] {msg}")

    # ── 内部辅助 ────────────────────────────────────────────

    def _applyChannelState(self, idx: int, ch: PwmChannelInfo):
        """根据 PwmChannelInfo 更新单路 UI 控件状态（仅 fetch 响应时调用）"""
        grp = self._ch_groups[idx]
        freq_spin = self._ch_freq_spins[idx]
        duty_slider = self._ch_duty_sliders[idx]
        duty_spin = self._ch_duty_spins[idx]
        enable_check = self._ch_enable_checks[idx]

        # 存储最新 fetch 状态
        self._last_channel_states[idx] = ch

        # 更新标题（使用真实 MCU 通道号）
        mcu_ch = self._baseChannel + idx
        status = "[占用]" if ch.occupied else "[空闲]"
        grp.setTitle(f"通道 {mcu_ch + 1} {status}")

        # 频率控件
        freq_spin.blockSignals(True)
        freq_spin.setRange(ch.freq_min, ch.freq_max)
        freq_spin.setValue(ch.freq_current)
        freq_spin.setEnabled(ch.occupied and ch.freq_adjustable)
        freq_spin.blockSignals(False)

        # 占空比控件
        duty_pct = ch.duty_current / 100.0
        duty_enabled = ch.occupied and ch.duty_adjustable

        duty_slider.blockSignals(True)
        duty_slider.setRange(ch.duty_min, ch.duty_max)
        duty_slider.setValue(ch.duty_current)
        duty_slider.setEnabled(duty_enabled)
        duty_slider.blockSignals(False)

        duty_spin.blockSignals(True)
        duty_spin.setRange(ch.duty_min / 100.0, ch.duty_max / 100.0)
        duty_spin.setValue(duty_pct)
        duty_spin.setEnabled(duty_enabled)
        duty_spin.blockSignals(False)

        # 启用控件
        enable_check.blockSignals(True)
        enable_check.setChecked(ch.enabled)
        enable_check.setEnabled(ch.occupied)
        enable_check.blockSignals(False)

        # 最终根据输出连接状态调整
        self._applyChannelEnableState(idx)

