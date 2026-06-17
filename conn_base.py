from qtpy.QtCore import Qt, QPointF, QSizeF, QRectF
from qtpy.QtGui import QPolygonF, QBrush, QImage, QFont, QFontMetrics, QColor
from qtpy.sip import isdeleted

from nodeeditor.node_content_widget import QDMNodeContentWidget
from nodeeditor.node_node import Node
from nodeeditor.node_graphics_socket import QDMGraphicsSocket
from nodeeditor.node_socket import Socket
from nodeeditor.node_graphics_edge import QDMGraphicsEdge
from nodeeditor.node_edge import Edge
from nodeeditor.node_scene import Scene
from nodeeditor.node_scene_clipboard import SceneClipboard
from nodeeditor.node_edge_validators import (
    edge_validator_debug,
    edge_cannot_connect_two_outputs_or_two_inputs,
    edge_cannot_connect_input_and_output_of_same_node
)
from nodeeditor.node_graphics_node import QDMGraphicsNode
from nodeeditor.node_socket import LEFT_CENTER, RIGHT_CENTER, LEFT_BOTTOM, LEFT_TOP, RIGHT_BOTTOM, RIGHT_TOP

from conn_utils import easyInfo, easyError, easyWarning, easyDebug, easyMsg, isRealSignal, isQObjectInstanceMethod, disconnectAll
from conn_conf import GlobalSettingManager


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

        percent = 0.5
        arrow_pos = path.pointAtPercent(percent)
        angle = -(path.angleAtPercent(percent) + (180 if self.edge.end_socket.is_output else 0))

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
        self._is_loaded = False

    def getGraphicsEdgeClass(self):
        return ConnGraphicsEdge
    
    def setConnInfo(self, signal_owner, signal_key, slot_owner, slot_key):
        self._signal_owner = signal_owner
        self._signal_key = signal_key
        self._slot_owner = slot_owner
        self._slot_key = slot_key
        self._is_loaded = True

    def getConnInfo(self):
        return self._signal_owner, self._signal_key, self._slot_owner, self._slot_key
    
    def clearConnInfo(self):
        self._signal_owner = None
        self._signal_key = None
        self._slot_owner = None
        self._slot_key = None
        self._is_loaded = False

    def signalConnect(self, ctype) -> bool:
        try:
            if not isinstance(ctype, int):
                raise TypeError("ctype 必须是 int 类型")

            if not self._is_loaded:
                raise ValueError("无法执行连接, 还未加载连接信息")

            signal_owner = self._signal_owner
            signal_key = self._signal_key
            slot_owner = self._slot_owner
            slot_key = self._slot_key

            if isdeleted(slot_owner.content):
                raise RuntimeError("槽对象已删除失败")
            
            if isdeleted(signal_owner.content):
                raise RuntimeError("信号对象已删除")

            signal = signal_owner.getSignal(signal_key)
            slot = slot_owner.getSlot(slot_key)

            signal.connect(slot, ctype)

            self._is_loaded = True
            easyDebug(f"连接成功: 信号键:\"{signal_key}\" --> 键:\"{slot_key}\", 类型 {ctype}")
            
            return True
        except Exception as e:
            easyError(f"连接失败:")
            easyError(e)
            self.markError()
            
            return False

    def signalDisconnect(self) -> bool:
        try:
            if not self._is_loaded:
                raise ValueError("无法执行断开, 还未加载连接信息")
            
            signal_owner = self._signal_owner
            signal_key = self._signal_key
            slot_owner = self._slot_owner
            slot_key = self._slot_key

            if isdeleted(slot_owner.content):
                raise RuntimeError("槽对象已删除失败")
            
            if isdeleted(signal_owner.content):
                raise RuntimeError("信号对象已删除")

            signal = signal_owner.getSignal(signal_key)
            slot = slot_owner.getSlot(slot_key)

            signal.disconnect(slot)

            easyDebug(f"断开成功: 信号键:\"{signal_key}\" --X 键:\"{slot_key}\"")
            
            return True
        except Exception as e:
            easyError(f"断开失败:")
            easyError(e)
            self.markError()

            return False

    def signalReconnect(self, ctype):
        # 短路特性可以保证前面失败后面不执行
        return self.signalDisconnect() and self.signalConnect(ctype)

    def markError(self):
        self._is_error = True
        self.grEdge.changeColor(Qt.red)

    def isError(self):
        return self._is_error
    
    def isLoaded(self):
        return self._is_loaded

    def deserialize(self, data:dict, hashmap:dict={}, restore_id:bool=True, *args, **kwargs) -> bool:
        """在这里完成重新连接操作"""
        if restore_id: self.id = data['id']
        self.start_socket = hashmap[data['start']]
        self.end_socket = hashmap[data['end']]
        self.edge_type = data['edge_type']

        # 重新连接信号槽槽
        self.start_socket.node.onEdgeConnectionChanged(self)
        self.end_socket.node.onEdgeConnectionChanged(self)

class ConnSceneClipboard(SceneClipboard):
    def deserializeFromClipboard(self, data: dict, *args, **kwargs):
        """
        复制于原库代码, 它的边反序列化硬编码了Edge类型, 这里必须全部复制更改
        """

        hashmap = {}

        # calculate mouse pointer - scene position
        view = self.scene.getView()
        mouse_scene_pos = view.last_scene_mouse_position

        # calculate selected objects bbox and center
        minx, maxx, miny, maxy = 10000000,-10000000, 10000000,-10000000
        for node_data in data['nodes']:
            if 'pos_x' in node_data and 'pos_y' in node_data:
                x, y = node_data['pos_x'], node_data['pos_y']
            else:
                # added support if node pos serializes into `pos` instead of `pos_x` and `pos_y`
                x, y = node_data['pos']
            if x < minx: minx = x
            if x > maxx: maxx = x
            if y < miny: miny = y
            if y > maxy: maxy = y

        # add width and height of a node
        maxx -= 180
        maxy += 100

        relbboxcenterx = (minx + maxx) / 2 - minx
        relbboxcentery = (miny + maxy) / 2 - miny

        if False:
            print (" *** PASTA:")
            print("Copied boudaries:\n\tX:", minx, maxx, "   Y:", miny, maxy)
            print("\tbbox_center:", relbboxcenterx, relbboxcentery)

        # calculate the offset of the newly creating nodes
        mousex, mousey = mouse_scene_pos.x(), mouse_scene_pos.y()

        # create each node
        created_nodes = []

        self.scene.setSilentSelectionEvents()

        self.scene.doDeselectItems()

        for node_data in data['nodes']:
            new_node = self.scene.getNodeClassFromData(node_data)(self.scene)
            new_node.deserialize(node_data, hashmap, restore_id=False, *args, **kwargs)
            created_nodes.append(new_node)

            # readjust the new nodeeditor's position

            # new node's current position
            posx, posy = new_node.pos.x(), new_node.pos.y()
            newx, newy = mousex + posx - minx, mousey + posy - miny

            new_node.setPos(newx, newy)

            new_node.doSelect()

            if False:
                print("** PASTA SUM:")
                print("\tMouse pos:", mousex, mousey)
                print("\tnew node pos:", posx, posy)
                print("\tFINAL:", newx, newy)

        # create each edge
        if 'edges' in data:
            for edge_data in data['edges']:
                new_edge = ConnEdge(self.scene)
                new_edge.deserialize(edge_data, hashmap, restore_id=False, *args, **kwargs)


        self.scene.setSilentSelectionEvents(False)

        # store history
        self.scene.history.storeHistory("Pasted elements in scene", setModified=True)

        return created_nodes



class ConnScene(Scene):

    clipboardClass = ConnSceneClipboard

    def getEdgeClass(self):
        return ConnEdge

    def reconnectAll(self, ctype):
        for edge in self.edges:
            edge.signalReconnect(ctype)


def edge_type_validator(input, output) -> bool:
    signal_socket = output if output.is_output else input
    slot_socket = input if output.is_output else output

    if signal_socket.argsType != slot_socket.argsType:
        signalArgs = ', '.join([t.__name__ for t in signal_socket.argsType])
        slotArgs = ', '.join([t.__name__ for t in slot_socket.argsType])

        easyError(f"信号与槽参数类型不匹配, 信号参数类型 ({signalArgs}), 槽参数类型 ({slotArgs})")
        return False
    
    return True


# ConnEdge.registerEdgeValidator(edge_validator_debug)
ConnEdge.registerEdgeValidator(edge_type_validator)
ConnEdge.registerEdgeValidator(edge_cannot_connect_two_outputs_or_two_inputs)
# ConnEdge.registerEdgeValidator(edge_cannot_connect_input_and_output_of_same_node)





class ConnGraphicsNode(QDMGraphicsNode):
    def initSizes(self):
        super().initSizes()

        self.handle_margin = 10
        self.handle_size = 20

        self.is_resizeable = True
        self.is_resizing = False
        self.resize_start_pos = None
        self.original_width = None
        self.original_height = None

        self.edge_roundness = 2
        self.edge_padding = 0 + 2 * self.handle_margin
        self.title_horizontal_padding = 8
        self.title_vertical_padding = 10

        if self.content is not None:
            self.width = self.content.size().width() + self.edge_padding * 2
            self.height = self.content.size().height() + self.edge_padding * 2 + self.title_height
            

    def initAssets(self):
        super().initAssets()

    def getHandleRect(self):
        return QRectF(
            self.width - self.handle_size - self.handle_margin, 
            self.height - self.handle_size - self.handle_margin, 
            self.handle_size, 
            self.handle_size
        )


    def paint(self, painter, QStyleOptionGraphicsItem, widget=None):
        super().paint(painter, QStyleOptionGraphicsItem, widget)

        if not self.is_resizeable: 
            return

        painter.setPen(self._pen_selected)
        handle_rect = self.getHandleRect()
        
        painter.drawRect(handle_rect)

    def mousePressEvent(self, event):
        pos = event.pos()
        handle_rect = self.getHandleRect()
        
        if handle_rect.contains(pos):
            self.is_resizing = True
            self.resize_start_pos = pos
            self.original_width = self.width
            self.original_height = self.height

            self.setCursor(Qt.SizeFDiagCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_resizing:
            delta = event.pos() - self.resize_start_pos

            contentMinSize = self.content.minimumSizeHint() if self.content is not None else QSizeF(64, 64)

            self.width = min(max(self.original_width + delta.x(), contentMinSize.width() + self.edge_padding * 2, 64), 2048)
            self.height = min(max(self.original_height + delta.y(), contentMinSize.height() + self.edge_padding * 2 + self.title_height, 64), 2048)
            self.prepareGeometryChange()  # 重要：通知视图 boundingRect 改变
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def updateContentIdealGeometry(self):
        if self.content is not None:
            self.content.setGeometry(
                int(self.edge_padding), 
                int(self.title_height) + int(self.edge_padding),
                int(self.width - 2 * self.edge_padding), 
                int(self.height - 2 * self.edge_padding - self.title_height)
            )

    def mouseReleaseEvent(self, event):
        if self.is_resizing:
            self.is_resizing = False

            self.node.scene.history.storeHistory("Node resized", setModified=True)

            for socket in self.node.inputs + self.node.outputs:
                socket.setSocketPosition()
            self.node.updateConnectedEdges()
            self.updateContentIdealGeometry()

            self.unsetCursor()
            event.accept()
        else:
            super().mouseReleaseEvent(event)



class ConnGraphicsSocket(QDMGraphicsSocket):
    def initAssets(self):
        super().initAssets()

        self._text = ""
        self._text_offset = 1
        self._text_font = QFont()
        self._text_font.setPointSize(10)
        self._text_metrics = QFontMetrics(self._text_font)
        self._text_margin = 5

    def paint(self, painter, QStyleOptionGraphicsItem, widget=None):
        super().paint(painter, QStyleOptionGraphicsItem, widget)
       
        painter.setFont(self._text_font)
        painter.setPen(self._color_background)
        
        text_width = self._text_metrics.horizontalAdvance(self._text)

        text_x = self.radius - ((text_width + 2 * self.radius if self._text_offset > 0 else 0) + self._text_margin * self._text_offset)
        text_y = self.radius / 2   
  
        painter.drawText(int(text_x), int(text_y), self._text)


    def setText(self, text):
        self._text = text

    def getText(self) -> str:
        return self._text


class ConnSocketConf:
    def __init__(self, 
        socketType = 1,
        key = None,
        name: str = None,
        tooltip: str = None,
        argsType: tuple[type] = (),
                 ):
        if not isinstance(key, str) or key.strip() == "":
            raise TypeError("key 必须是非空字符串")
        
        if not isinstance(argsType, tuple):
            raise TypeError("argsType 必须是元组")

        self.socketType = socketType
        self.key = key
        self.tooltip = tooltip
        self.name = name
        self.argsType = argsType

class ConnSocket(Socket):
    Socket_GR_Class = ConnGraphicsSocket
    
    def setToolTip(self, tooltip):
        self.grSocket.setToolTip(tooltip)

    def toolTip(self) -> str:
        return self.grSocket.toolTip()
    
    def setText(self, text):
        self.grSocket.setText(text)

    def text(self) -> str:
        return self.grSocket.text()
    
    def setSocketPosition(self):
        super().setSocketPosition()
        self.grSocket._text_offset = 1 if self.position == LEFT_BOTTOM or self.position == LEFT_TOP or self.position == LEFT_CENTER else -1

    def setArgsType(self, argsType: tuple[type]):
        self.argsType = argsType

    def getArgsType(self) -> tuple[type]:
        return self.argsType

class ConnNodeContentWidget(QDMNodeContentWidget):
    def cleanup(self):
        easyWarning(f"{self.__class__.__name__} 未实现 cleanup 方法...")

    def initUI(self):
        self.resize(200, 120)

    def setNodeSize(self, width: int, height: int) -> None:
        """设置节点框初始大小（UI 职责）

        替代在 initUI() 中调用 self.resize(W, H) 的方式。
        子类在 initUI() 中调用此方法，Node 构造完成后自动同步
        grNode/content/proxy 三方尺寸。

        Args:
            width: 期望的节点框宽度（像素）
            height: 期望的节点框高度（像素）
        """
        self._pending_node_size = (width, height)

class ConnNode(Node):
    tppath = None
    icon = ""
    name = "未定义的名称"
    tooltip = "未定义的提示"
    conn_title = "未定义的标题"

    NodeContent_class = ConnNodeContentWidget
    GraphicsNode_class = ConnGraphicsNode
    Socket_class = ConnSocket

    def __init__(self, scene, 
        signalsConf: list[ConnSocketConf] = [],
        slotsConf: list[ConnSocketConf] = [],
    ):
        try:
            if any(not isinstance(conf, ConnSocketConf) for conf in signalsConf):
                raise TypeError("signalsConf 必须是 ConnSocketConf 类型的列表")

            if any(not isinstance(conf, ConnSocketConf) for conf in slotsConf):
                raise TypeError("slotsConf 必须是 ConnSocketConf 类型的列表")
            
            self._signals = {}
            self._slots = {}

            
            self.signalsConf = signalsConf
            self.slotsConf = slotsConf

            inputs = [socket.socketType for socket in slotsConf]
            outputs = [socket.socketType for socket in signalsConf]

            super().__init__(scene, self.__class__.conn_title, inputs, outputs)

            for idx, conf in enumerate(signalsConf):
                tooltip = f"{conf.tooltip}\n参数: ({', '.join([arg.__name__ for arg in conf.argsType])})"
                self.outputs[idx].setToolTip(tooltip)
                self.outputs[idx].setText(conf.name if conf.name else conf.key)
                self.outputs[idx].setArgsType(conf.argsType)

            for idx, conf in enumerate(slotsConf):
                tooltip = f"{conf.tooltip}\n参数: ({', '.join([arg.__name__ for arg in conf.argsType])})"
                self.inputs[idx].setToolTip(tooltip)
                self.inputs[idx].setText(conf.name if conf.name else conf.key)
                self.inputs[idx].setArgsType(conf.argsType)

            # ── 应用 Content 存储的初始大小 ────────────────
            if hasattr(self.content, '_pending_node_size'):
                w, h = self.content._pending_node_size
                self.grNode.width = w
                self.grNode.height = h
                self.grNode.prepareGeometryChange()
                self.grNode.updateContentIdealGeometry()
                for sock in self.inputs + self.outputs:
                    sock.setSocketPosition()
                self.updateConnectedEdges()

        except Exception as e:
            easyError(f"{self.__class__.__name__} 实例初始化时错误:")
            easyError(e)
            raise e # 继续冒泡给默认框架处理



    def registerSignal(self, key, signal):
        if not isRealSignal(signal):
            easyError(f"{self.__class__.__name__} 实例注册信号键: \"{key}\" 时, 信号对象不是 Qt 信号对象")
            return

        if key in self._signals and self._signals[key] != signal:
            easyWarning(f"{self.__class__.__name__} 实例重复注册信号键: \"{key}\" 将覆盖已注册信号")

        self._signals[key] = signal

    def registerSlot(self, key, slot):
        if not callable(slot):
            easyError(f"{self.__class__.__name__} 实例注册槽键: \"{key}\" 时, 槽函数对象不是可调用对象")
            return
        
        if not isQObjectInstanceMethod(slot):
            easyWarning(f"{self.__class__.__name__} 实例注册槽键: \"{key}\" 时, 槽函数对象可能不是 QObject 实例方法")
        
        if key in self._slots and self._slots[key] != slot:
            easyWarning(f"{self.__class__.__name__} 实例重复注册槽键: \"{key}\" 将覆盖已注册槽函数")

        self._slots[key] = slot

    def initSettings(self):
        super().initSettings()

        # 允许多个输入
        self.input_multi_edged = True 
        self.input_socket_position = LEFT_CENTER
        self.output_socket_position = RIGHT_CENTER

    def onInputChanged(self, socket=None):
        pass

    def onEdgeConnectionChanged(self, new_edge):
        """删除时假设槽的生命周期 = slot_owner.content 的生命周期"""

        start_socket = new_edge.start_socket
        end_socket = new_edge.end_socket
        
        isConnectAction = start_socket is not None and end_socket is not None

        if isConnectAction:
            signal_socket = start_socket if start_socket.is_output else end_socket
            slot_socket = end_socket if start_socket.is_output else start_socket
            if signal_socket.node is not self:
                return
            
            signal_owner = None
            signal_key = None
            slot_owner = None
            slot_key = None
            try:
                signal_owner = signal_socket.node
                signal_key = self.getSignalKeyBySocket(signal_socket)
                slot_owner = slot_socket.node
                slot_key = slot_socket.node.getSlotKeyBySocket(slot_socket)
            except Exception as e:
                easyError(f"{self.__class__.__name__}.onEdgeConnectionChanged: 创建连接失败:")
                easyError(e)
                new_edge.markError()

                return
            
            new_edge.setConnInfo(signal_owner, signal_key, slot_owner, slot_key)
            new_edge.signalConnect(GlobalSettingManager.instance().connectionType)
        else:
            if new_edge.isError() or not new_edge.isLoaded():
                return

            signal_owner, signal_key, slot_owner, slot_key = new_edge.getConnInfo()
            if signal_owner is not self:
                return
            
            new_edge.signalDisconnect()
            new_edge.clearConnInfo()


    def getSlotKeyBySocket(self, socket) -> str| None:
        idx = self.inputs.index(socket)
        return self.slotsConf[idx].key
        
    def getSignalKeyBySocket(self, socket) -> str| None:
        idx = self.outputs.index(socket)
        return self.signalsConf[idx].key

    def getSlot(self, key) -> "function":
        if key not in self._slots:
            raise ValueError(f"获取槽键: \"{key}\" 时, 槽函数对象不存在")
        return self._slots[key]

    def getSignal(self, key) -> "pyqtSignal":
        if key not in self._signals:
            raise ValueError(f"获取信号键: \"{key}\" 时, 信号对象不存在")
        return self._signals[key]

    def serialize(self):
        res = super().serialize()
        res['tppath'] = self.__class__.tppath
        res['width'] = self.grNode.width
        res['height'] = self.grNode.height
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        self.grNode.width = data.get('width', self.grNode.width)
        self.grNode.height = data.get('height', self.grNode.height)
        self.grNode.prepareGeometryChange()  # 重要：通知视图 boundingRect 改变
        self.grNode.update()
        self.grNode.updateContentIdealGeometry()

        for socket in self.inputs + self.outputs:
            socket.setSocketPosition()

        self.updateConnectedEdges()
        

        return res
    
    def remove(self):
        self.content.cleanup()
        super().remove()