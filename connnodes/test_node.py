from qtpy.QtWidgets import QTextEdit, QLabel, QVBoxLayout
from PyQt5.QtCore import pyqtSignal
from nodeeditor.node_content_widget import QDMNodeContentWidget

from conn_conf import register_node, set_node_display
from conn_base import ConnNode, ConnSocketConf
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

    def cleanup(self):
        ...


@register_node()
class Test_TextInputNode(ConnNode):
    tppath = ("测试", "文本输入器")
    icon = "icons/emitter.png"
    name = "文本输入器"
    tooltip = "可以编辑文本并自动发送文本"
    conn_title = "文本输入器"

    NodeContent_class = Test_TextInputContent

    def __init__(self, scene):
        super().__init__(scene, 
            signalsConf = [
                ConnSocketConf(
                    socketType=2,
                    key="textNotify",
                    tooltip="当文本输入改变时发送",
                    name="文本",
                    argsType=(str,)
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

    def cleanup(self):
        ...

@register_node()
class Test_TextShowNode(ConnNode):
    tppath = ("测试", "文本显示器")
    icon = "icons/receiver.png"
    name = "文本显示器"
    tooltip = "可以显示文本"
    conn_title = "文本显示器"

    NodeContent_class = Test_TextShowContent

    def __init__(self, scene):
        super().__init__(scene, 
            slotsConf=[
                ConnSocketConf(
                    socketType=1,
                    key="setText",
                    tooltip="通过此显示文本",
                    name="显示",
                    argsType=(str,)
                )
            ]
        )
        self.registerSlot("setText", self.content.textShow.setText)
        easyInfo("测试文本显示器创建成功！")


set_node_display(
    tppath=("测试目录", ), 
    tooltip="测试目录的提示", 
    icon="icons/sub.png")