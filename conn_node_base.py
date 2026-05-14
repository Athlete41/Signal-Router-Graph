from qtpy.QtGui import QImage
from qtpy.QtCore import QRectF
from qtpy.QtWidgets import QLabel

from nodeeditor.node_node import Node
from nodeeditor.node_content_widget import QDMNodeContentWidget
from nodeeditor.node_graphics_node import QDMGraphicsNode
from nodeeditor.node_socket import LEFT_CENTER, RIGHT_CENTER
from logger import SimpleLogger, logger


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




class ConnNode(Node):
    icon = ""
    tppath = ("未定义的路径", )
    name = "未定义的名称"
    tooltip = "未定义的提示"
    
    conn_title = "未定义的标题"

    GraphicsNode_class = ConnGraphicsNode
    NodeContent_class = QDMNodeContentWidget

    def __init__(self, scene, inputs=[2,2], outputs=[1]):
        super().__init__(scene, self.__class__.conn_title, inputs, outputs)

        self.value = None

        # it's really important to mark all nodes Dirty by default
        self.markDirty()


    def initSettings(self):
        super().initSettings()
        self.input_socket_position = LEFT_CENTER
        self.output_socket_position = RIGHT_CENTER

    def onInputChanged(self, socket=None):
        SimpleLogger.instance().debug("%s::__onInputChanged" % self.__class__.__name__)
        logger.debug("%s::__onInputChanged" % self.__class__.__name__)
        self.markDirty()
        self.eval()


    def onEdgeConnectionChanged(self, new_edge):
        SimpleLogger.instance().debug("%s::__onEdgeConnectionChanged" % self.__class__.__name__)
        logger.debug("%s::__onEdgeConnectionChanged" % self.__class__.__name__)

        return super().onEdgeConnectionChanged(new_edge)


    def serialize(self):
        res = super().serialize()
        res['tppath'] = self.__class__.tppath
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)

        SimpleLogger.instance().debug("Deserialized ConnNode '%s'" % self.__class__.__name__)
        logger.debug("Deserialized ConnNode '%s'" % self.__class__.__name__)
        return res