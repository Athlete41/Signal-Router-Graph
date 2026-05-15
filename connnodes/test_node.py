from conn_conf import register_node, set_node_display
from conn_node_base import ConnNode, ConnGraphicsNode, ConnNodeContentWidget
from utils import LEVEL, logging, easyInfo
from qtpy.QtWidgets import QTextEdit, QLabel, QVBoxLayout
from PyQt5.QtCore import pyqtSignal

if LEVEL <= logging.DEBUG:
    class Test_TextEdit(QTextEdit):
        textNotify = pyqtSignal(str)

        def __init__(self, parent=None):
            super().__init__(parent)
            self.textChanged.connect(self.on_textChanged)

        def on_textChanged(self):
            self.textNotify.emit(self.toPlainText())


    class Test_TextInputContent(ConnNodeContentWidget):
        def initUI(self):
            self.Layout = QVBoxLayout(self)
            self.setLayout(self.Layout)
            self.textEdit = Test_TextEdit(self)
            self.Layout.addWidget(self.textEdit)


    @register_node(("测试", "文本输入器"))
    class Test_TextInputNode(ConnNode):
        tppath = ("测试", "文本输入器")
        icon = "icons/in.png"
        name = "文本输入器"
        tooltip = "提供一个文本信号发送str类型"
        conn_title = "文本输入器"

        NodeContent_class = Test_TextInputContent

        def __init__(self, scene):
            super().__init__(scene, inputs=[], outputs=[2], inputBinds=[], outputBinds=["textNotify"])
            self.registerSignal("textNotify", self.content.textEdit.textNotify)
            easyInfo("测试文本输入器创建成功！")

        def initInnerClasses(self):
            super().initInnerClasses()
            self.grNode.height = 120 # 设置高度


    class Test_TextShowContent(ConnNodeContentWidget):
        def initUI(self):
            self.Layout = QVBoxLayout(self)
            self.setLayout(self.Layout)
            self.textShow = QLabel(self)
            self.Layout.addWidget(self.textShow)

    @register_node(("测试", "文本显示器"))
    class Test_TextShowNode(ConnNode):
        tppath = ("测试", "文本显示器")
        icon = "icons/out.png"
        name = "文本显示器"
        tooltip = "测试节点的提示"
        conn_title = "测试节点的标题"

        NodeContent_class = Test_TextShowContent

        def __init__(self, scene):
            super().__init__(scene, inputs=[1], outputs=[], inputBinds=["setText"], outputBinds=[])
            self.registerSlot("setText", self.content.textShow.setText)
            easyInfo("测试文本显示器创建成功！")


    set_node_display(
        tppath=("测试目录", ), 
        tooltip="测试目录的提示", 
        icon="icons/sub.png")