"""
PWM 控制器 — 内容部件

PwmControllerWidget (ConnNodeContentWidget)
  ├── 静态 UI: .ui 文件加载 (操作栏 + 起始通道 + 4 路扁平单行通道 + 状态标签)
  ├── 嵌套 _Worker(QObject) 持有 _PwmCore（工作线程）
  ├── 4 个 per-channel 输出信号 + 4 个 per-channel dict 输入槽
  └── 定时 fetch QTimer (主线程)
"""

from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import (
    Qt, QThread, QObject, pyqtSignal, pyqtSlot,
    QMetaObject, QTimer, QByteArray,
)

from .pwm_core import _PwmCore
from .pwm_protocol import PwmChannelInfo
from .pwm_controller_ui import Ui_PwmController
from conn_utils import easyError, easyWarning, easyDebug, ThreadManager
from conn_base import ConnNodeContentWidget


# 状态标签颜色常量（避免多处写死样式字符串）
_ST_COLORS = {
    "ok": "#0a0",
    "pending": "#cc0",
    "error": "#e44",
    "disconnected": "#e84",
    "idle": "#888",
}


class PwmControllerWidget(ConnNodeContentWidget):
    """PWM 控制器内容部件（主线程）"""

    # ── Per-channel 输出信号 ────────────────────────────────

    ch1Send = pyqtSignal(QByteArray)
    ch2Send = pyqtSignal(QByteArray)
    ch3Send = pyqtSignal(QByteArray)
    ch4Send = pyqtSignal(QByteArray)

    # 索引访问用信号元组（与 CHANNEL_COUNT 保持一致）
    CH_SIGNALS = (ch1Send, ch2Send, ch3Send, ch4Send)

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

        # 2. 加载 .ui 布局
        self.ui = Ui_PwmController()
        self.ui.setupUi(self)
        self.layout().setContentsMargins(6, 6, 6, 4)

        # 全局暗色主题样式（与串口节点一样的模式）
        self.setStyleSheet("""
            PwmControllerWidget {
                background-color: #0a0a0a;
            }
            QSpinBox, QDoubleSpinBox {
                background-color: #202020;
                color: #e0e0e0;
                border: 1px solid #404040;
                padding: 1px 2px;
                min-height: 20px;
                max-height: 20px;
            }
            QSpinBox::up-button, QDoubleSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 14px;
                background-color: #353535;
                border: 1px solid #505050;
                border-left: none;
                border-bottom: none;
                border-top-right-radius: 3px;
            }
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 14px;
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
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #5aadff;
                width: 10px;
                margin: -4px 0;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: #2a6a9a;
                border-radius: 2px;
            }
            QCheckBox {
                color: #c0c0c0;
                spacing: 4px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
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
                padding: 2px 8px;
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

        # 3. 起始通道偏移
        self._baseChannel = 0

        # 4. 组装 per-channel 控件列表（保持与 for 循环兼容）
        self._ch_labels: list[QLabel] = [
            self.ui.ch1Label, self.ui.ch2Label,
            self.ui.ch3Label, self.ui.ch4Label,
        ]
        self._ch_freq_spins = [
            self.ui.ch1Freq, self.ui.ch2Freq,
            self.ui.ch3Freq, self.ui.ch4Freq,
        ]
        self._ch_duty_sliders = [
            self.ui.ch1DutySlider, self.ui.ch2DutySlider,
            self.ui.ch3DutySlider, self.ui.ch4DutySlider,
        ]
        self._ch_duty_spins = [
            self.ui.ch1DutySpin, self.ui.ch2DutySpin,
            self.ui.ch3DutySpin, self.ui.ch4DutySpin,
        ]
        self._ch_enable_checks = [
            self.ui.ch1Enable, self.ui.ch2Enable,
            self.ui.ch3Enable, self.ui.ch4Enable,
        ]

        # 5. Per-channel 状态追踪
        self._last_channel_states: list = [None] * self.CHANNEL_COUNT

        # 6. 自动刷新定时器（主线程）
        self._autoFetchTimer = QTimer(self)
        self._autoFetchTimer.timeout.connect(self._core.fetchPwmInfo)

        # 7. 连接信号
        self._connectSignals()

        # 8. 初始状态（所有通道禁用，尚无输出连接）
        self._updateAllConnectionStates()

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

    def _isOutputConnected(self, local_idx: int) -> bool:
        """检查输出端口是否有边连接（替代冗余缓存）"""
        try:
            node_outputs = self.node.outputs
            if 0 <= local_idx < len(node_outputs):
                return len(node_outputs[local_idx].edges) > 0
        except (AttributeError, IndexError):
            pass
        return False

    # ── 信号连接 ────────────────────────────────────────────

    def _connectSignals(self):
        """连接 Widget ↔ Core 的所有信号"""
        # Core → Widget（跨线程，AutoConnection 自动投递）
        self._core.commandForChannel.connect(self._onCommandForChannel)
        self._core.commandBroadcast.connect(self._onCommandBroadcast)
        self._core.pwmInfoReady.connect(self._onInfoReceived)
        self._core.setAckReady.connect(self._onAckReceived)
        self._core.errorReceived.connect(self._onErrorReceived)

        # UI 控件事件
        self.ui.fetchBtn.clicked.connect(self._onFetchClicked)
        self.ui.autoRefreshCheck.toggled.connect(self._onAutoRefreshToggled)
        self.ui.intervalSpin.valueChanged.connect(self._onIntervalChanged)
        self.ui.baseSpin.valueChanged.connect(self._onBaseChannelChanged)

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

    def _updateAllConnectionStates(self):
        """批量对所有通道重新评估输出连接状态（initUI 时使用）"""
        for i in range(self.CHANNEL_COUNT):
            self._applyChannelEnableState(i)

    def setChOutputConnected(self, local_idx: int, connected: bool = True):
        """单路输出端口连接状态变更（由 Node.onEdgeConnectionChanged 调用）

        重新评估该通道的控件启用状态（实际以 edges 为准）。
        fetchBtn 的启用状态由 Node._updateFetchButtonState 控制。
        """
        if 0 <= local_idx < self.CHANNEL_COUNT:
            self._applyChannelEnableState(local_idx)

    def _applyChannelEnableState(self, local_idx: int):
        """根据 fetch 数据 + 输出连接状态，决定通道控件的最终启用状态"""
        ch_info = self._last_channel_states[local_idx]
        has_output = self._isOutputConnected(local_idx)

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
        self._updateStatus("正在查询 PWM 信息...", "pending")
        self._core.fetchPwmInfo()

    def _onAutoRefreshToggled(self, checked: bool):
        """定时刷新开关"""
        if checked:
            interval = self.ui.intervalSpin.value()
            self._autoFetchTimer.start(interval)
            self._updateStatus(f"定时刷新中（间隔 {interval} ms）...", "ok")
        else:
            self._autoFetchTimer.stop()
            self._updateStatus("定时刷新已停止", "idle")

    def _onIntervalChanged(self, val: int):
        """刷新间隔改变"""
        if self._autoFetchTimer.isActive():
            self._autoFetchTimer.setInterval(val)
            self.ui.statusLabel.setText(f"定时刷新中（间隔 {val} ms）...")

    def _onBaseChannelChanged(self, base: int):
        """起始通道偏移改变 → 更新通道标签和提示"""
        self._baseChannel = base
        for i in range(self.CHANNEL_COUNT):
            mcu_ch = base + i
            # 保留之前 fetch 的占用状态（如果有）
            prev = self._last_channel_states[i]
            suffix = f"[{'占' if prev.occupied else '空'}]" if prev else ""
            self._ch_labels[i].setText(f"{mcu_ch + 1}{suffix}")
        self.ui.baseHintLabel.setText(f"→ 通道 {base+1}~{base+4}")
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
        self.CH_SIGNALS[local].emit(packet)

    @pyqtSlot(QByteArray)
    def _onCommandBroadcast(self, packet: QByteArray):
        """Core 广播命令（FETCH） → 所有 4 路输出端口"""
        for sig in self.CH_SIGNALS:
            sig.emit(packet)

    @pyqtSlot(list)
    def _onInfoReceived(self, channels: list):
        """收到 fetch 响应 → 更新所有通道 UI"""
        self._updateStatus(f"已获取 {len(channels)} 个 PWM 通道", "ok")

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

        self._updateStatus(msg, "error")
        easyError(f"[PWM] {msg}")

    # ── 状态标签辅助 ────────────────────────────────────────

    def _updateStatus(self, text: str, color_key: str):
        """统一更新状态标签文本和颜色（color_key 来自 _ST_COLORS）"""
        color = _ST_COLORS.get(color_key, "#888")
        self.ui.statusLabel.setText(text)
        self.ui.statusLabel.setStyleSheet(
            f"color: {color}; font-size: 11px; padding: 2px;")

    # ── 内部辅助 ────────────────────────────────────────────

    def _applyChannelState(self, idx: int, ch: PwmChannelInfo):
        """根据 PwmChannelInfo 更新单路 UI 控件状态（仅 fetch 响应时调用）"""
        freq_spin = self._ch_freq_spins[idx]
        duty_slider = self._ch_duty_sliders[idx]
        duty_spin = self._ch_duty_spins[idx]
        enable_check = self._ch_enable_checks[idx]

        # 存储最新 fetch 状态
        self._last_channel_states[idx] = ch

        # 更新标签（使用真实 MCU 通道号 + 占用状态）
        mcu_ch = self._baseChannel + idx
        status = "[占]" if ch.occupied else "[空]"
        self._ch_labels[idx].setText(f"{mcu_ch + 1}{status}")

        # 频率控件（setEnabled 由末尾的 _applyChannelEnableState 统一处理）
        freq_spin.blockSignals(True)
        freq_spin.setRange(ch.freq_min, ch.freq_max)
        freq_spin.setValue(ch.freq_current)
        freq_spin.blockSignals(False)

        # 占空比控件
        duty_pct = ch.duty_current / 100.0

        duty_slider.blockSignals(True)
        duty_slider.setRange(ch.duty_min, ch.duty_max)
        duty_slider.setValue(ch.duty_current)
        duty_slider.blockSignals(False)

        duty_spin.blockSignals(True)
        duty_spin.setRange(ch.duty_min / 100.0, ch.duty_max / 100.0)
        duty_spin.setValue(duty_pct)
        duty_spin.blockSignals(False)

        # 启用控件
        enable_check.blockSignals(True)
        enable_check.setChecked(ch.enabled)
        enable_check.blockSignals(False)

        # 最终根据输出连接状态调整
        self._applyChannelEnableState(idx)
