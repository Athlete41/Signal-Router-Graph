from nodeeditor.node_socket import LEFT_BOTTOM, RIGHT_BOTTOM

from .tcp_client_widget import TcpClient_Widget
from .tcp_server_widget import TcpServer_Widget
from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf
from PyQt5.QtCore import QByteArray


# ═══════════════════════════════════════════════
# TCP 客户端节点
# ═══════════════════════════════════════════════

@register_node()
class TcpClientNode(ConnNode):
    tppath = ("数据源", "TCP客户端")
    icon = "icons/er.png"
    name = "TCP客户端"
    tooltip = "TCP 客户端，连接到远程服务器进行数据收发（多线程）"
    conn_title = "TCP客户端"

    NodeContent_class = TcpClient_Widget

    def __init__(self, scene):
        super().__init__(scene,
            slotsConf=[
                ConnSocketConf(
                    socketType=1,
                    key="sendText",
                    tooltip="通过 TCP 发送文本数据",
                    name="发送-文本",
                    argsType=(str,)
                ),
                ConnSocketConf(
                    socketType=1,
                    key="sendData",
                    tooltip="通过 TCP 发送二进制数据",
                    name="发送-数据",
                    argsType=(QByteArray,)
                ),
            ],
            signalsConf=[
                ConnSocketConf(
                    socketType=2,
                    key="received",
                    tooltip="TCP 接收到的数据（QByteArray）",
                    name="接收-数据",
                    argsType=(QByteArray,)
                ),
            ]
        )
        self.registerSlot("sendText", self.content.client.sendText)
        self.registerSlot("sendData", self.content.client.sendData)
        self.registerSignal("received", self.content.client.received)

    def initSettings(self):
        super().initSettings()
        self.input_multi_edged = True
        self.input_socket_position = LEFT_BOTTOM
        self.output_socket_position = RIGHT_BOTTOM

    def serialize(self):
        res = super().serialize()
        res["host"] = self.content.hostInput.text()
        res["port"] = self.content.portInput.value()
        res["info_log"] = self.content.infoCb.isChecked()
        res["warn_log"] = self.content.warnCb.isChecked()
        res["error_log"] = self.content.errCb.isChecked()
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        self.content.hostInput.setText(data.get("host", "127.0.0.1"))
        self.content.portInput.setValue(data.get("port", 8080))
        self.content.infoCb.setChecked(data.get("info_log", True))
        self.content.warnCb.setChecked(data.get("warn_log", True))
        self.content.errCb.setChecked(data.get("error_log", True))
        return res


# ═══════════════════════════════════════════════
# TCP 服务端节点
# ═══════════════════════════════════════════════

@register_node()
class TcpServerNode(ConnNode):
    tppath = ("数据源", "TCP服务端")
    icon = "icons/er.png"
    name = "TCP服务端"
    tooltip = "TCP 服务端，接受客户端连接并进行数据收发（多线程）"
    conn_title = "TCP服务端"

    NodeContent_class = TcpServer_Widget

    def __init__(self, scene):
        super().__init__(scene,
            slotsConf=[
                ConnSocketConf(
                    socketType=1,
                    key="sendTextToAll",
                    tooltip="向所有已连接的客户端发送文本",
                    name="广播-文本",
                    argsType=(str,)
                ),
                ConnSocketConf(
                    socketType=1,
                    key="sendDataToAll",
                    tooltip="向所有已连接的客户端发送二进制数据",
                    name="广播-数据",
                    argsType=(QByteArray,)
                ),
            ],
            signalsConf=[
                ConnSocketConf(
                    socketType=2,
                    key="received",
                    tooltip="服务端接收到的客户端数据（QByteArray）",
                    name="接收-数据",
                    argsType=(QByteArray,)
                ),
                ConnSocketConf(
                    socketType=2,
                    key="clientConnected",
                    tooltip="新客户端连接 (clientId, address)",
                    name="客户端连接",
                    argsType=(int, str)
                ),
                ConnSocketConf(
                    socketType=2,
                    key="clientDisconnected",
                    tooltip="客户端断开连接 (clientId)",
                    name="客户端断开",
                    argsType=(int,)
                ),
            ]
        )
        self.registerSlot("sendTextToAll", self.content.server.sendTextToAll)
        self.registerSlot("sendDataToAll", self.content.server.sendToAll)
        self.registerSignal("received", self.content.server.received)
        self.registerSignal("clientConnected", self.content.server.clientConnected)
        self.registerSignal("clientDisconnected", self.content.server.clientDisconnected)

    def initSettings(self):
        super().initSettings()
        self.input_multi_edged = True
        self.input_socket_position = LEFT_BOTTOM
        self.output_socket_position = RIGHT_BOTTOM

    def serialize(self):
        res = super().serialize()
        res["host"] = self.content.hostInput.text()
        res["port"] = self.content.portInput.value()
        res["info_log"] = self.content.infoCb.isChecked()
        res["warn_log"] = self.content.warnCb.isChecked()
        res["error_log"] = self.content.errCb.isChecked()
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        self.content.hostInput.setText(data.get("host", "0.0.0.0"))
        self.content.portInput.setValue(data.get("port", 8080))
        self.content.infoCb.setChecked(data.get("info_log", True))
        self.content.warnCb.setChecked(data.get("warn_log", True))
        self.content.errCb.setChecked(data.get("error_log", True))
        return res
