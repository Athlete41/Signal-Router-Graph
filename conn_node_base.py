from qtpy.QtGui import QImage
from qtpy.QtCore import QRectF

from nodeeditor.node_socket import Socket
from nodeeditor.node_graphics_socket import QDMGraphicsSocket
from nodeeditor.node_node import Node
from nodeeditor.node_graphics_node import QDMGraphicsNode
from nodeeditor.node_content_widget import QDMNodeContentWidget
from nodeeditor.node_socket import LEFT_CENTER, RIGHT_CENTER
from utils import easyInfo, easyError, easyWarning, easyDebug, easyMsg


class ConnGraphicsNode(QDMGraphicsNode):
    def initSizes(self):
        super().initSizes()
        self.width = 160
        self.height = 74
        self.edge_roundness = 6
        self.edge_padding = 0
        self.title_horizontal_padding = 8
        self.title_vertical_padding = 10

    def initAssets(self):
        super().initAssets()
        self.icons = QImage("icons/status_icons.png")

    def paint(self, painter, QStyleOptionGraphicsItem, widget=None):
        super().paint(painter, QStyleOptionGraphicsItem, widget)

        offset = 24.0
        if self.node.isDirty(): offset = 0.0
        if self.node.isInvalid(): offset = 48.0

        painter.drawImage(
            QRectF(-10, -10, 24.0, 24.0),
            self.icons,
            QRectF(offset, 0, 24.0, 24.0)
        )

class ConnGraphicsSocket(QDMGraphicsSocket):
    ...

class ConnSocket(Socket):
    Socket_GR_Class = ConnGraphicsSocket
    ...

class ConnNodeContentWidget(QDMNodeContentWidget):
    def __init__(self, node, parent = None):
        super().__init__(node, parent)

class ConnNode(Node):
    icon = ""
    tppath = ("未定义的路径", )
    name = "未定义的名称"
    tooltip = "未定义的提示"
    
    conn_title = "未定义的标题"

    GraphicsNode_class = ConnGraphicsNode
    NodeContent_class = ConnNodeContentWidget
    Socket_class = ConnSocket

    def __init__(self, scene, 
        inputs=[], 
        outputs=[],
        inputBinds=[],
        outputBinds=[],
    ):
        self._signals = {}
        if len(inputBinds) != len(inputs):
            easyError(f"{self.__class__.__name__}::__init__ 输入绑定数量与输入数量不匹配")
        if len(outputBinds) != len(outputs):
            easyError(f"{self.__class__.__name__}::__init__ 输出绑定数量与输出数量不匹配")

        super().__init__(scene, self.__class__.conn_title, inputs, outputs)


    def registerSignal(self, key, signal):
        if key not in self._signals:
            self._signals[key] = signal
        else:
            easyWarning(f"{self.__class__.__name__} 实例重复注册信号键: {key}")


    def initSettings(self):
        super().initSettings()

        # 运行多个输入
        self.input_multi_edged = True 
        self.input_socket_position = LEFT_CENTER
        self.output_socket_position = RIGHT_CENTER

    def onInputChanged(self, socket=None):
        pass

    def onEdgeConnectionChanged(self, new_edge):
        easyDebug("%s::__onEdgeConnectionChanged" % self.__class__.__name__)

        if new_edge.start_socket is not None and new_edge.end_socket is not None:
            easyDebug(f"创建边, 输入节点: {new_edge.start_socket.node}, 输出节点: {new_edge.end_socket.node}")

            if new_edge.start_socket.node is self:
                easyDebug(f"端口索引: {self.outputs.index(new_edge.start_socket)}")
        else:
            easyDebug(f"删除边, 输入端口: {new_edge.start_socket}, 输出端口: {new_edge.end_socket}")

        return super().onEdgeConnectionChanged(new_edge)


    def serialize(self):
        res = super().serialize()
        res['tppath'] = self.__class__.tppath
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)

        easyDebug("Deserialized ConnNode '%s'" % self.__class__.__name__)
        return res