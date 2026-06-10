"""
PWM 控制器 — 工作线程核心逻辑 (_PwmCore)

_QObject 运行在专用 QThread 中，负责：
  - 协议包构造（调用 pwm_protocol 的 build_* 函数）
  - 响应解析与分发（decode_frame → 按命令码分发）
  - Fetch 超时管理

所有 @pyqtSlot 方法可被跨线程信号调用（AutoConnection 自动处理）。
"""

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QByteArray

from . import pwm_protocol as proto
from conn_utils import easyError, easyWarning, easyDebug


class _PwmCore(QObject):
    """PWM 控制器核心（工作线程）"""

    # ── 信号（由 Widget 监听）─────────────────────────────

    commandForChannel = pyqtSignal(int, QByteArray)
    """通道专用命令: (mcu_channel_idx, packet) → Widget 路由到对应输出端口"""

    commandBroadcast = pyqtSignal(QByteArray)
    """广播命令（FETCH_PWM_INFO 等） → Widget 发送到所有输出端口"""

    pwmInfoReady = pyqtSignal(list)
    """FETCH 响应解析完成，携带 list[PwmChannelInfo]"""

    setAckReady = pyqtSignal(int, int, object)
    """SET 命令确认: (channel_idx, cmd_code, value)"""

    errorReceived = pyqtSignal(int, int)
    """错误: (error_code, channel_idx)"""

    # ── 内部状态 ──────────────────────────────────────────

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fetch_timeout_timer = QTimer(self)
        self._fetch_timeout_timer.setSingleShot(True)
        self._fetch_timeout_timer.timeout.connect(self._onFetchTimeout)

    # ── 公共槽 ────────────────────────────────────────────

    @pyqtSlot()
    def fetchPwmInfo(self):
        """发送 FETCH_PWM_INFO 命令"""
        packet = proto.build_fetch_info()
        easyDebug("[PWM] 发送 FETCH_PWM_INFO 命令")
        self.commandBroadcast.emit(packet)
        # 启动 2s 超时定时器
        self._fetch_timeout_timer.start(2000)

    @pyqtSlot(int, int)
    def setFreq(self, channel_idx: int, freq_hz: int):
        """发送 SET_PWM_FREQ 命令"""
        packet = proto.build_set_freq(channel_idx, freq_hz)
        easyDebug(f"[PWM] MCU通道{channel_idx} 设置频率: {freq_hz} Hz")
        self.commandForChannel.emit(channel_idx, packet)

    @pyqtSlot(int, int)
    def setDuty(self, channel_idx: int, duty: int):
        """发送 SET_PWM_DUTY 命令

        Args:
            channel_idx: MCU 通道索引
            duty: 占空比 0-10000
        """
        packet = proto.build_set_duty(channel_idx, duty)
        easyDebug(f"[PWM] MCU通道{channel_idx} 设置占空比: {duty / 100:.2f}%")
        self.commandForChannel.emit(channel_idx, packet)

    @pyqtSlot(int, bool)
    def setEnable(self, channel_idx: int, enable: bool):
        """发送 SET_PWM_ENABLE 命令"""
        packet = proto.build_set_enable(channel_idx, enable)
        state = "启用" if enable else "禁用"
        easyDebug(f"[PWM] MCU通道{channel_idx} {state}")
        self.commandForChannel.emit(channel_idx, packet)

    @pyqtSlot(QByteArray)
    def handleResponse(self, data: QByteArray):
        """接收 MCU 响应，解码并分发"""
        result = proto.decode_frame(data)
        if result is None:
            easyWarning("[PWM] 收到无效帧（校验失败或格式错误），已丢弃")
            return

        cmd, payload = result

        if cmd == proto.CMD_PWM_INFO_REPORT:
            # 停止超时定时器
            self._fetch_timeout_timer.stop()
            channels = proto.decode_info_report(payload)
            if channels is None:
                easyError("[PWM] INFO_REPORT 解析失败")
                return
            easyDebug(f"[PWM] 收到 INFO_REPORT: {len(channels)} 个通道")
            self.pwmInfoReady.emit(channels)

        elif cmd == proto.CMD_PWM_SET_ACK:
            ack = proto.decode_set_ack(payload)
            if ack is None:
                easyWarning("[PWM] SET_ACK 解析失败")
                return
            easyDebug(f"[PWM] 收到 ACK: ch={ack['ch_idx']+1} cmd=0x{ack['cmd']:02X} val={ack['value']}")
            self.setAckReady.emit(ack["ch_idx"], ack["cmd"], ack["value"])

        elif cmd == proto.CMD_PWM_ERROR:
            err = proto.decode_error(payload)
            if err is None:
                easyWarning("[PWM] ERROR 帧解析失败")
                return
            err_code, ch_idx = err
            msg = proto.get_error_message(err_code)
            easyError(f"[PWM] MCU 返回错误: {msg} (通道{ch_idx+1 if ch_idx < 0xFFFF else '?'})")
            self.errorReceived.emit(err_code, ch_idx)

        else:
            easyWarning(f"[PWM] 收到未知命令: 0x{cmd:02X}")

    @pyqtSlot()
    def shutdown(self):
        """清理资源"""
        self._fetch_timeout_timer.stop()
        easyDebug("[PWM] Core 已关闭")

    # ── 内部方法 ──────────────────────────────────────────

    @pyqtSlot()
    def _onFetchTimeout(self):
        """FETCH 超时回调"""
        easyWarning("[PWM] FETCH_PWM_INFO 超时 (2s 未收到响应)")
        self.errorReceived.emit(0xFE, -1)  # 0xFE = 自定义超时错误码
