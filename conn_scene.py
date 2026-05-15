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
        self._arrow_offset_percent = 1

        self._arrow_color = Qt.white



    def paint(self, painter, QStyleOptionGraphicsItem, widget=None):
        super().paint(painter, QStyleOptionGraphicsItem, widget)

        if self.edge.end_socket is None:
            return

        path = self.path()
        if path.isEmpty():
            return

        percent = self._arrow_offset_percent
        if percent >= 1.0:
            percent = 0.92
        arrow_pos = path.pointAtPercent(percent)
        angle = path.angleAtPercent(percent)

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

    def getGraphicsEdgeClass(self):
        return ConnGraphicsEdge

class ConnScene(Scene):
    def getEdgeClass(self):
        return ConnEdge



ConnEdge.registerEdgeValidator(edge_validator_debug)
ConnEdge.registerEdgeValidator(edge_cannot_connect_two_outputs_or_two_inputs)
# ConnEdge.registerEdgeValidator(edge_cannot_connect_input_and_output_of_same_node)



