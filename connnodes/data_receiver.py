from qtpy.QtWidgets import QTextBrowser, QSpinBox, QVBoxLayout, QLabel, QHBoxLayout
from qtpy.QtGui import QTextCursor
from PyQt5.QtCore import QByteArray

from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf
from conn_base import ConnNodeContentWidget



class DataReceiverContent(ConnNodeContentWidget):
    def initUI(self):
        layout = QVBoxLayout(self)
        self.textBrowser = QTextBrowser(self)
        layout_2 = QHBoxLayout()
        self.maxLineLabel = QLabel(f"最大行数: 无限", self)
        self.maxLineSpinBox = QSpinBox(self)

        layout_2.addWidget(self.maxLineLabel)
        layout_2.addWidget(self.maxLineSpinBox)

        self.setLayout(layout)
        layout.addWidget(self.textBrowser)
        layout.addLayout(layout_2)

        self.maxLineSpinBox.setMinimum(0)
        self.maxLineSpinBox.setMaximum(9999)

        self.maxLineSpinBox.valueChanged.connect(self.maxLineSpinBoxHandler)

        self.resize(200, 200)


    def maxLineSpinBoxHandler(self, value: int):
        if value == 0:
            self.maxLineLabel.setText(f"最大行数: 无限")
        else:
            self.maxLineLabel.setText(f"最大行数: ")

        self.textBrowser.document().setMaximumBlockCount(value)

    def receivedDataHandler(self, data: QByteArray):
        text = bytes(data).decode("utf-8", errors='ignore') 
        self.textBrowser.moveCursor(QTextCursor.MoveOperation.End)
        self.textBrowser.insertPlainText(text)

    def receivedTextHandler(self, text: str):
        self.textBrowser.moveCursor(QTextCursor.MoveOperation.End)
        self.textBrowser.insertPlainText(text)

    def cleanup(self):
        ...

@register_node()
class DataReceiverNode(ConnNode):
    tppath = ("可视化", "接收器")
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
                    key="receivedDataHandler",
                    tooltip="接收 QByteArray 类型数据并解析为 utf-8 文本字符串",
                    name="数据",
                    argsType=(QByteArray,)
                ),
                ConnSocketConf(
                    socketType=1,
                    key="receivedTextHandler",
                    tooltip="接收文本字符串",
                    name="文本",
                    argsType=(str,)
                ),
            ]
        )
        self.registerSlot("receivedDataHandler", self.content.receivedDataHandler)
        self.registerSlot("receivedTextHandler", self.content.receivedTextHandler)

    def serialize(self):
        res = super().serialize()
        res['max_line_count'] = self.content.maxLineSpinBox.value()
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        self.content.maxLineSpinBox.setValue(data.get('max_line_count', 0))
        return res
    