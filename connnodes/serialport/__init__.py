from nodeeditor.node_socket import LEFT_BOTTOM, RIGHT_BOTTOM

from .serialport_widget import SerialPort_Widget
from conn_conf import register_node
from conn_node_base import ConnNode, ConnSocketDisplay


@register_node(("数据源", "串口"))
class SerialPortNode(ConnNode):
    tppath = ("数据源", "串口")
    icon = "icons/in.png"
    name = "串口"
    tooltip = """串口数据源:
信号: 
received (QByteArray, dict)
槽:
sendData (QByteArray)
"""
    conn_title = "串口"

    NodeContent_class = SerialPort_Widget

    def __init__(self, scene):
        super().__init__(scene, 
            inputs=[1], 
            inputBinds=["sendData"],
            inputDisplays=[ConnSocketDisplay(tooltip="槽参数: QByteArray", name="发送")],

            outputs=[2], 
            outputBinds=["received"],
            outputDisplays=[ConnSocketDisplay(tooltip="信号参数: QByteArray, dict", name="数据")]
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
