from nodeeditor.node_socket import LEFT_BOTTOM, RIGHT_BOTTOM

from .serialport_widget import SerialPort_Widget
from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf
from PyQt5.QtCore import QByteArray
from PyQt5.QtSerialPort import QSerialPort


@register_node()
class SerialPortNode(ConnNode):
    tppath = ("数据源", "简单串口")
    icon = "icons/er.png"
    name = "简单串口"
    tooltip = "简单的串口数据源, 提供读写的端口"
    conn_title = "简单串口"

    NodeContent_class = SerialPort_Widget

    def __init__(self, scene):
        super().__init__(scene, 
            slotsConf = [
                ConnSocketConf(
                    socketType=1,
                    key="sendText",
                    tooltip="通过此向串口发送文本",
                    name="发送-文本",
                    argsType=(str,)
                ),


                ConnSocketConf(
                    socketType=1,
                    key="sendData",
                    tooltip="通过此向串口发送数据",
                    name="发送-数据",
                    argsType=(QByteArray,)
                )
            ],

            signalsConf=[
                ConnSocketConf(
                    socketType=2,
                    key="received",
                    tooltip="通过此获取串口接收的数据",
                    name="数据",
                    argsType=(QByteArray,)
                )
            ]
        )
        self.registerSignal("received", self.content.dataSource.received)
        self.registerSlot("sendData", self.content.dataSource.sendData)
        self.registerSlot("sendText", self.content.dataSource.sendText)

        self.content: SerialPort_Widget

    def initSettings(self):
        super().initSettings()

        # 运行多个输入
        self.input_multi_edged = True 
        self.input_socket_position = LEFT_BOTTOM
        self.output_socket_position = RIGHT_BOTTOM


    def serialize(self):
        res = super().serialize()
        device = self.content.dataSource.device

        res["baud_rate"] = device.baudRate()
        res["data_bits"] = device.dataBits()
        res["parity"] = device.parity()
        res["stop_bits"] = device.stopBits()
        res["flow_control"] = device.flowControl()

        res["info_log_enable"] = self.content.ui.infoLogBtn.isChecked()
        res["warning_log_enable"] = self.content.ui.warningLogBtn.isChecked()
        res["error_log_enable"] = self.content.ui.errorLogBtn.isChecked()
        
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)

        device = self.content.dataSource.device
        device.setBaudRate(data.get("baud_rate", 115200))
        device.setDataBits(data.get("data_bits", 8))
        device.setParity(data.get("parity", QSerialPort.NoParity))
        device.setStopBits(data.get("stop_bits", QSerialPort.OneStop))
        device.setFlowControl(data.get("flow_control", QSerialPort.NoFlowControl))

        self.content.ui.infoLogBtn.setChecked(data.get("info_log_enable", False))
        self.content.ui.warningLogBtn.setChecked(data.get("warning_log_enable", False))
        self.content.ui.errorLogBtn.setChecked(data.get("error_log_enable", False))

        return res