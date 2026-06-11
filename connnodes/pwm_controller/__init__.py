"""
PWM 控制器节点

固定 4 路 PWM 通道控制。通过外接串口节点与 MCU 通信。
支持两种控制方式:
  1. 手动调节 UI 控件（频率/占空比/启用）
  2. 自动控制（通过 per-channel dict 输入端口接收指令，不更新 UI）

可配置起始通道偏移 (base channel)，多节点实例控制不同通道段。

端口（9个）:
  - 输出: ch1_send ~ ch4_send (QByteArray) — per-channel 协议包
  - 输入: ch1_ctrl ~ ch4_ctrl (dict)         — per-channel 自动控制
  - 输入: received (QByteArray)               — 共享串口响应接收
"""

from .pwm_widget import PwmControllerWidget
from conn_conf import register_node, set_node_display
from conn_base import ConnNode, ConnSocketConf
from nodeeditor.node_socket import LEFT_CENTER, RIGHT_CENTER
from PyQt5.QtCore import QByteArray


# 注册 "控制" 分类的显示元数据
set_node_display(
    tppath=("控制",),
    name="控制",
    tooltip="控制类节点（PWM 等）",
    icon="icons/sub.png",
)


@register_node()
class PWMControllerNode(ConnNode):
    tppath = ("控制", "PWM控制器")
    icon = "icons/pwm.png"
    name = "PWM控制器"
    tooltip = (
        "PWM 控制器节点（固定 4 路），通过串口与 MCU 通信。\n"
        "• 每通道独立端口：CH1~4 发送(QByteArray) + CH1~4 控制(dict)\n"
        "• 可配起始通道偏移 → 多节点实例控不同通道段\n"
        "• 手动调节：频率/占空比/启用\n"
        "• 自动控制：通过 chN_ctrl 端口接收 dict 指令\n"
        "• 定时刷新：周期性同步 MCU 状态"
    )
    conn_title = "PWM 控制器"

    NodeContent_class = PwmControllerWidget

    CHANNEL_COUNT = 4

    def __init__(self, scene):
        super().__init__(scene,
            slotsConf=[
                # ── Per-channel dict 控制输入 ──
                ConnSocketConf(
                    socketType=1, key="ch1_ctrl", name="CH1控制",
                    tooltip="通道1 dict 控制: {\"freq\": 1000} / {\"duty\": 50.0} / {\"enable\": True} / {\"cmd\": \"fetch\"}",
                    argsType=(dict,)),
                ConnSocketConf(
                    socketType=1, key="ch2_ctrl", name="CH2控制",
                    tooltip="通道2 dict 控制", argsType=(dict,)),
                ConnSocketConf(
                    socketType=1, key="ch3_ctrl", name="CH3控制",
                    tooltip="通道3 dict 控制", argsType=(dict,)),
                ConnSocketConf(
                    socketType=1, key="ch4_ctrl", name="CH4控制",
                    tooltip="通道4 dict 控制", argsType=(dict,)),
                # ── 共享串口响应接收 ──
                ConnSocketConf(
                    socketType=1, key="received", name="接收",
                    tooltip="接收串口返回的 QByteArray 协议数据（所有通道共享）",
                    argsType=(QByteArray,)),
            ],
            signalsConf=[
                # ── Per-channel 协议包输出 ──
                ConnSocketConf(
                    socketType=2, key="ch1_send", name="CH1发送",
                    tooltip="通道1 PWM 协议包输出 (QByteArray)", argsType=(QByteArray,)),
                ConnSocketConf(
                    socketType=2, key="ch2_send", name="CH2发送",
                    tooltip="通道2 PWM 协议包输出 (QByteArray)", argsType=(QByteArray,)),
                ConnSocketConf(
                    socketType=2, key="ch3_send", name="CH3发送",
                    tooltip="通道3 PWM 协议包输出 (QByteArray)", argsType=(QByteArray,)),
                ConnSocketConf(
                    socketType=2, key="ch4_send", name="CH4发送",
                    tooltip="通道4 PWM 协议包输出 (QByteArray)", argsType=(QByteArray,)),
            ]
        )

        # 注册输出信号
        self.registerSignal("ch1_send", self.content.ch1Send)
        self.registerSignal("ch2_send", self.content.ch2Send)
        self.registerSignal("ch3_send", self.content.ch3Send)
        self.registerSignal("ch4_send", self.content.ch4Send)

        # 注册输入槽
        self.registerSlot("ch1_ctrl", self.content.handleCh1Ctrl)
        self.registerSlot("ch2_ctrl", self.content.handleCh2Ctrl)
        self.registerSlot("ch3_ctrl", self.content.handleCh3Ctrl)
        self.registerSlot("ch4_ctrl", self.content.handleCh4Ctrl)
        self.registerSlot("received", self.content._core.handleResponse)

        self.content: PwmControllerWidget

    def initSettings(self):
        super().initSettings()
        self.input_socket_position = LEFT_CENTER
        self.output_socket_position = RIGHT_CENTER
        self.input_multi_edged = True

    def onEdgeConnectionChanged(self, new_edge):
        """追踪每路输出端口连接状态"""
        super().onEdgeConnectionChanged(new_edge)
        # outputs[0]~[3] 对应 ch1_send~ch4_send
        for i in range(self.CHANNEL_COUNT):
            if i < len(self.outputs):
                edge_count = len(self.outputs[i].edges)
                self.content.setChOutputConnected(i, edge_count > 0)
        self._updateFetchButtonState()

    def _updateFetchButtonState(self):
        """检查是否至少有一个输出端口已连接"""
        has_any = any(
            len(self.outputs[i].edges) > 0
            for i in range(min(self.CHANNEL_COUNT, len(self.outputs)))
        )
        self.content._fetchBtn.setEnabled(has_any)
        if not has_any:
            self.content._autoRefreshCheck.setChecked(False)
            self.content._autoFetchTimer.stop()
            self.content._statusLabel.setText("未连接 — 请先连接至少一个发送端口")
            self.content._statusLabel.setStyleSheet(
                "color: #e84; font-size: 11px; padding: 2px;")

    def serialize(self):
        res = super().serialize()
        # 保存 4 路通道的 UI 状态
        res["pwm_channels"] = self.content.getChannelsData()
        # 保存定时刷新设置
        res["auto_refresh"] = self.content._autoRefreshCheck.isChecked()
        res["refresh_interval"] = self.content._intervalSpin.value()
        # 保存起始通道偏移
        res["base_channel"] = self.content._baseSpin.value()
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        # 恢复起始通道（需在恢复通道数据之前）
        base = data.get("base_channel", 0)
        self.content._baseSpin.setValue(base)  # 触发 _onBaseChannelChanged → 更新标题
        # 恢复通道 UI（不发送命令）
        channels_data = data.get("pwm_channels", [])
        if channels_data:
            self.content.restoreFromSerializedData(channels_data)
        # 恢复定时刷新设置
        interval = data.get("refresh_interval", 1000)
        self.content._intervalSpin.setValue(interval)
        auto_refresh = data.get("auto_refresh", False)
        if auto_refresh:
            # 延迟重新启用（等连接恢复后用户手动开启）
            self.content._autoRefreshCheck.setChecked(False)
        return res
