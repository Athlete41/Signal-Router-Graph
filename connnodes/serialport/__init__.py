from nodeeditor.node_socket import LEFT_BOTTOM, RIGHT_BOTTOM

from .serialport_widget import SerialPort_Widget
from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf
from PyQt5.QtCore import QByteArray


@register_node()
class SerialPortNode(ConnNode):
    tppath = ("数据源", "串口")
    icon = "icons/er.png"
    name = "串口"
    tooltip = "简单的串口数据源, 提供读写的端口"
    conn_title = "串口"

    NodeContent_class = SerialPort_Widget

    def __init__(self, scene):
        super().__init__(scene, 
            slotsConf = [
                ConnSocketConf(
                    socketType=1,
                    key="sendData",
                    tooltip="通过此向串口发送数据",
                    name="发送",
                    argsType=(QByteArray,)
                )
            ],

            signalsConf=[
                ConnSocketConf(
                    socketType=2,
                    key="received",
                    tooltip="通过此获取串口接收的数据",
                    name="数据",
                    argsType=(QByteArray, dict)
                )
            ]
        )
        self.registerSignal("received", self.content.dataSource.received)
        self.registerSlot("sendData", self.content.dataSource.sendData)
   

    def initInnerClasses(self):
        super().initInnerClasses()
        self.grNode.height = 350
        self.grNode.width = 300

    def initSettings(self):
        super().initSettings()

        # 运行多个输入
        self.input_multi_edged = True 
        self.input_socket_position = LEFT_BOTTOM
        self.output_socket_position = RIGHT_BOTTOM
