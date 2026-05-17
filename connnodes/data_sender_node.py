from qtpy.QtWidgets import QTextEdit, QHBoxLayout, QVBoxLayout, QPushButton, QCheckBox
from PyQt5.QtCore import pyqtSignal, QByteArray
from nodeeditor.node_content_widget import QDMNodeContentWidget

from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf
from conn_utils import easyError



class DataSenderContent(QDMNodeContentWidget):
    sendDataNotify = pyqtSignal(QByteArray)
    sendTextNotify = pyqtSignal(str)

    def initUI(self):
        layout = QVBoxLayout(self)
        self.textEdit = QTextEdit(self)
        self.autoLineBreak = QCheckBox(self)
        self.sendBtn = QPushButton("发送", self)

        self.setLayout(layout)
        layout.addWidget(self.textEdit)
        layout.addWidget(self.autoLineBreak)
        layout.addWidget(self.sendBtn)

        self.autoLineBreak.setText("自动新行")
        self.sendBtn.clicked.connect(self.sendData)

        # TODO 暂时没找到细致修改全局样式的方法, 这里先简单处理
        self.setStyleSheet("""                 
QCheckBox {
    color: #e0e0e0;
}
""")


    def sendData(self):
        text = self.textEdit.toPlainText() + ("\n" if self.autoLineBreak.isChecked() else "")
        if text != "":
            self.sendDataNotify.emit(QByteArray(text.encode("utf-8")))
            self.sendTextNotify.emit(text)


    def cleanup(self):
        ...

@register_node()
class DataSenderNode(ConnNode):
    tppath = ("数据源", "数据发送器")
    icon = "icons/emitter.png"
    name = "数据发送器"
    tooltip = "可以发送 QByteArray 类型数据"
    conn_title = "数据发送器"

    NodeContent_class = DataSenderContent

    def __init__(self, scene):
        super().__init__(scene,
            signalsConf=[
                ConnSocketConf(
                    socketType=2,
                    key="sendDataNotify",
                    tooltip="会将字符串转换为 QByteArray 类型后发送",
                    name="数据",
                    argsType=(QByteArray,)
                ),

                ConnSocketConf(
                    socketType=2,
                    key="sendTextNotify",
                    tooltip="直接发送文本字符串",
                    name="文本",
                    argsType=(str,)
                )
            ]
        )
        self.registerSignal("sendDataNotify", self.content.sendDataNotify)
        self.registerSignal("sendTextNotify", self.content.sendTextNotify)



    def initInnerClasses(self):
        super().initInnerClasses()
        self.grNode.height = 200 # 设置高度
        self.grNode.width = 200
