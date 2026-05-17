from qtpy.QtWidgets import QTextBrowser, QSpinBox, QVBoxLayout
from qtpy.QtGui import QTextCursor
from PyQt5.QtCore import QByteArray

from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf
from conn_base import ConnNodeContentWidget



class DataReceiverContent(ConnNodeContentWidget):
    def initUI(self):
        layout = QVBoxLayout(self)
        self.textBrowser = QTextBrowser(self)
        self.maxLineSpinBox = QSpinBox(self)

        self.setLayout(layout)
        layout.addWidget(self.textBrowser)
        layout.addWidget(self.maxLineSpinBox)
        self.maxLineSpinBox.setMinimum(0)
        self.maxLineSpinBox.setMaximum(9999)

        self.maxLineSpinBox.valueChanged.connect(self.maxLineSpinBoxHandler)

        self.resize(200, 200)


    def maxLineSpinBoxHandler(self, value: int):
        self.textBrowser.document().setMaximumBlockCount(value)

    def receivedHandler(self, data: QByteArray):
        text = bytes(data).decode("utf-8", errors='ignore') 
        self.textBrowser.moveCursor(QTextCursor.MoveOperation.End)
        self.textBrowser.insertPlainText(text)

    def cleanup(self):
        ...

@register_node()
class DataReceiverNode(ConnNode):
    tppath = ("数据源", "接收器")
    icon = "icons/receiver.png"
    name = "接收器"
    tooltip = "可以接收 QByteArray 类型数据并解析为 utf-8 文本字符串"
    conn_title = "接收器"

    NodeContent_class = DataReceiverContent

    def __init__(self, scene):
        super().__init__(scene,
            slotsConf=[
                ConnSocketConf(
                    socketType=1,
                    key="receivedHandler",
                    tooltip="接收 QByteArray 类型数据并解析为 utf-8 文本字符串",
                    name="数据",
                    argsType=(QByteArray,)
                )
            ]
        )
        self.registerSlot("receivedHandler", self.content.receivedHandler)

    def serialize(self):
        res = super().serialize()
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        return res
    