from qtpy.QtCore import Qt, QPointF
from qtpy.QtGui import QPolygonF, QBrush

from nodeeditor.node_graphics_edge import QDMGraphicsEdge
from nodeeditor.node_edge import Edge
from nodeeditor.node_scene import Scene
from nodeeditor.node_edge_validators import (
    edge_validator_debug,
    edge_cannot_connect_two_outputs_or_two_inputs,
    edge_cannot_connect_input_and_output_of_same_node
)


class ConnGraphicsEdge(QDMGraphicsEdge):

    def initAssets(self):
        """箭头绘制相关"""
        super().initAssets()

        # ---- 箭头相关参数 ----
        self._arrow_size = 12.0         
        self._arrow_width = 12
        self._arrow_color = Qt.white



    def paint(self, painter, QStyleOptionGraphicsItem, widget=None):
        super().paint(painter, QStyleOptionGraphicsItem, widget)

        if self.edge.end_socket is None:
            return

        path = self.path()
        if path.isEmpty():
            return

        percent = 0.08 if self.edge.end_socket.is_output else 0.92
        arrow_pos = path.pointAtPercent(percent)
        angle = path.angleAtPercent(percent) + (180 if self.edge.end_socket.is_output else 0)

        triangle = QPolygonF([
            QPointF(self._arrow_size, 0),
            QPointF(0, -self._arrow_width / 2),
            QPointF(0, self._arrow_width / 2)
        ])

        painter.save()
        painter.translate(arrow_pos)
        painter.rotate(angle)
        painter.setBrush(QBrush(self._arrow_color))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(triangle)
        painter.restore()


class ConnEdge(Edge):
    # 使用独立的 edge_validators 列表，避免与父类的冲突
    edge_validators = [] 

    def __init__(self, scene, start_socket = None, end_socket = None, edge_type=...):
        super().__init__(scene, start_socket, end_socket, edge_type)
        self._signal_owner = None
        self._signal_key = None

        self._slot_owner = None
        self._slot_key = None

        self._is_error = False
        self._connect_type = Qt.AutoConnection

    def getGraphicsEdgeClass(self):
        return ConnGraphicsEdge
    
    def setConnInfo(self, signal_owner, signal_key, slot_owner, slot_key):
        self._signal_owner = signal_owner
        self._signal_key = signal_key
        self._slot_owner = slot_owner
        self._slot_key = slot_key

    def getConnInfo(self):
        return self._signal_owner, self._signal_key, self._slot_owner, self._slot_key
    
    def clearConnInfo(self):
        self._signal_owner = None
        self._signal_key = None
        self._slot_owner = None
        self._slot_key = None

    def markError(self):
        self._is_error = True
        self.grEdge.changeColor(Qt.red)

    def isError(self):
        return self._is_error

    def deserialize(self, data:dict, hashmap:dict={}, restore_id:bool=True, *args, **kwargs) -> bool:
        """在这里完成重新连接操作"""
        if restore_id: self.id = data['id']
        self.start_socket = hashmap[data['start']]
        self.end_socket = hashmap[data['end']]
        self.edge_type = data['edge_type']

        # 重新连接信号槽槽
        self.start_socket.node.onEdgeConnectionChanged(self)
        self.end_socket.node.onEdgeConnectionChanged(self)


class ConnScene(Scene):
    def getEdgeClass(self):
        return ConnEdge



# ConnEdge.registerEdgeValidator(edge_validator_debug)
ConnEdge.registerEdgeValidator(edge_cannot_connect_two_outputs_or_two_inputs)
# ConnEdge.registerEdgeValidator(edge_cannot_connect_input_and_output_of_same_node)



