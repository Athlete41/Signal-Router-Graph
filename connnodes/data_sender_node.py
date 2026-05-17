from qtpy.QtWidgets import QTextEdit, QHBoxLayout, QVBoxLayout, QPushButton, QCheckBox
from PyQt5.QtCore import pyqtSignal, QByteArray
from nodeeditor.node_content_widget import QDMNodeContentWidget

from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf
from conn_utils import easyError



class DataSenderContent(QDMNodeContentWidget):
    sendDataNotify = pyqtSignal(QByteArray)

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


@register_node()
class DataSenderNode(ConnNode):
    tppath = ("数据源", "数据发送器")
    icon = "icons/emitter.png"
    name = "数据发送器"
    tooltip = "提供一个数据信号发送QByteArray类型"
    conn_title = "数据发送器"

    NodeContent_class = DataSenderContent

    def __init__(self, scene):
        super().__init__(scene,
            signalsConf=[
                ConnSocketConf(
                    socketType=2,
                    key="sendDataNotify",
                    tooltip="参数: QByteArray",
                    name="QByteArray"
                )
            ]
        )
        try:
            self.registerSignal("sendDataNotify", self.content.sendDataNotify)
        except Exception as e:
            easyError(e)


    def initInnerClasses(self):
        super().initInnerClasses()
        self.grNode.height = 200 # 设置高度
        self.grNode.width = 200
