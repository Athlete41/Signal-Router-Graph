from qtpy.QtWidgets import QTextEdit, QLabel, QVBoxLayout
from PyQt5.QtCore import pyqtSignal
from nodeeditor.node_content_widget import QDMNodeContentWidget

from conn_conf import register_node, set_node_display
from conn_node_base import ConnNode, ConnSocketConf
from conn_utils import easyInfo



class Test_TextEdit(QTextEdit):
    textNotify = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.textChanged.connect(self.on_textChanged)

    def on_textChanged(self):
        self.textNotify.emit(self.toPlainText())


class Test_TextInputContent(QDMNodeContentWidget):
    def initUI(self):
        self.Layout = QVBoxLayout(self)
        self.setLayout(self.Layout)
        self.textEdit = Test_TextEdit(self)
        self.Layout.addWidget(self.textEdit)


@register_node(("测试", "文本输入器"))
class Test_TextInputNode(ConnNode):
    tppath = ("测试", "文本输入器")
    icon = "icons/emitter.png"
    name = "文本输入器"
    tooltip = "提供一个文本信号发送str类型"
    conn_title = "文本输入器"

    NodeContent_class = Test_TextInputContent

    def __init__(self, scene):
        super().__init__(scene, 
            signalsConf = [
                ConnSocketConf(
                    socketType=2,
                    key="textNotify",
                    tooltip="参数: str",
                    name="String"
                )
            ]
        )
        self.registerSignal("textNotify", self.content.textEdit.textNotify)
        easyInfo("测试文本输入器创建成功！")

    def initInnerClasses(self):
        super().initInnerClasses()
        self.grNode.height = 120 # 设置高度


class Test_TextShowContent(QDMNodeContentWidget):
    def initUI(self):
        self.Layout = QVBoxLayout(self)
        self.setLayout(self.Layout)
        self.textShow = QLabel(self)
        self.Layout.addWidget(self.textShow)

@register_node(("测试", "文本显示器"))
class Test_TextShowNode(ConnNode):
    tppath = ("测试", "文本显示器")
    icon = "icons/receiver.png"
    name = "文本显示器"
    tooltip = "提供一个槽接收str类型参数并显示"
    conn_title = "文本显示器"

    NodeContent_class = Test_TextShowContent

    def __init__(self, scene):
        super().__init__(scene, 
            slotsConf=[
                ConnSocketConf(
                    socketType=1,
                    key="setText",
                    tooltip="参数: str",
                    name="String"
                )
            ]
        )
        self.registerSlot("setText", self.content.textShow.setText)
        easyInfo("测试文本显示器创建成功！")


set_node_display(
    tppath=("测试目录", ), 
    tooltip="测试目录的提示", 
    icon="icons/sub.png")