from qtpy.QtGui import QImage
from qtpy.QtCore import QRectF, Qt
from qtpy import sip

from nodeeditor.node_socket import Socket
from nodeeditor.node_graphics_socket import QDMGraphicsSocket
from nodeeditor.node_node import Node
from nodeeditor.node_graphics_node import QDMGraphicsNode
from nodeeditor.node_content_widget import QDMNodeContentWidget
from nodeeditor.node_socket import LEFT_CENTER, RIGHT_CENTER
from utils import easyInfo, easyError, easyWarning, easyDebug, easyMsg, isRealSignal, isQObjectInstanceMethod, disconnect_all


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
        self._slots = {}
        if len(inputBinds) != len(inputs):
            easyError(f"{self.__class__.__name__}.__init__ 输入绑定数量与输入数量不匹配")
        if len(outputBinds) != len(outputs):
            easyError(f"{self.__class__.__name__}.__init__ 输出绑定数量与输出数量不匹配")
        if any(not isinstance(key, str) or key.strip() == "" for key in inputBinds):
            easyError(f"{self.__class__.__name__}.__init__ 输入绑定键必须是非空字符串")
        if any(not isinstance(key, str) or key.strip() == "" for key in outputBinds):
            easyError(f"{self.__class__.__name__}.__init__ 输出绑定键必须是非空字符串")

        self.inputBinds = inputBinds
        self.outputBinds = outputBinds

        super().__init__(scene, self.__class__.conn_title, inputs, outputs)


    def registerSignal(self, key, signal):
        if not isRealSignal(signal):
            easyError(f"{self.__class__.__name__} 实例注册信号键: {key} 时, 信号对象不是 Qt 信号对象")
            return

        if key in self._signals and self._signals[key] != signal:
            easyWarning(f"{self.__class__.__name__} 实例重复注册信号键: {key}, 将覆盖已注册信号")

        self._signals[key] = signal

    def registerSlot(self, key, slot):
        if not callable(slot):
            easyError(f"{self.__class__.__name__} 实例注册槽键: {key} 时, 槽函数对象不是可调用对象")
            return
        
        if not isQObjectInstanceMethod(slot):
            easyWarning(f"{self.__class__.__name__} 实例注册槽键: {key} 时, 槽函数对象不是 QObject 实例方法")
        
        if key in self._slots and self._slots[key] != slot:
            easyWarning(f"{self.__class__.__name__} 实例重复注册槽键: {key}, 将覆盖已注册槽函数")

        self._slots[key] = slot

    def initSettings(self):
        super().initSettings()

        # 运行多个输入
        self.input_multi_edged = True 
        self.input_socket_position = LEFT_CENTER
        self.output_socket_position = RIGHT_CENTER

    def onInputChanged(self, socket=None):
        pass

    def onEdgeConnectionChanged(self, new_edge):
        start_socket = new_edge.start_socket
        end_socket = new_edge.end_socket
        
        isConnectAction = start_socket is not None and end_socket is not None
        isDisconnectAction = not isConnectAction

        if isConnectAction:
            output_socket = start_socket if start_socket.is_output else end_socket
            input_socket = end_socket if start_socket.is_output else start_socket

            # 由信号提供者完成连接
            if output_socket.node is self:
                signal_owner = output_socket.node
                signal_key = self.getSlotKeyBySocket(output_socket)
                slot_owner = input_socket.node
                slot_key = input_socket.node.getSlotKeyBySocket(input_socket)


                isError = signal_key is None or slot_key is None
                if isError: 
                    easyError(f"{self.__class__.__name__}.onEdgeConnectionChanged: 信号提供者 {signal_owner}, 键:{signal_key} --> 槽提供者 {slot_owner}, 键:{slot_key} 连接失败")
                    new_edge.markError()
                    return
                
                signal = self._signals.get(signal_key, None)
                slot = slot_owner._slots.get(slot_key, None)

                isError = signal is None or slot is None
                if isError: 
                    new_edge.markError()
                    return

                signal.connect(slot, Qt.QueuedConnection)
                new_edge.setConnInfo(signal_owner, signal_key, slot_owner, slot_key)

                easyDebug(f"{self.__class__.__name__}.onEdgeConnectionChanged: 信号提供者 {signal_owner}, 键:{signal_key} --> 槽提供者 {slot_owner}, 键:{slot_key} 连接成功")

        if isDisconnectAction:
            if new_edge.isError():
                return

            signal_owner, signal_key, slot_owner, slot_key = new_edge.getConnInfo()
            if signal_owner is not self:
                return

            signal = self._signals.get(signal_key, None)
            slot = slot_owner._slots.get(slot_key, None)
            new_edge.clearConnInfo()

            if sip.isdeleted(slot_owner.content):
                easyDebug(f"{self.__class__.__name__}.onEdgeConnectionChanged: 槽提供者 {slot_owner}, 键:{slot_key} 已被删除")
            else:
                signal = self._signals.get(signal_key, None)
                if signal is None:
                    easyError(f"{self.__class__.__name__}.onEdgeConnectionChanged: 信号提供者 {signal_owner}, 键:{signal_key} 未注册, 无法断开连接")
                    return
     
                signal.disconnect(slot)





    def getSlotKeyBySocket(self, socket) -> str| None:
        idx = None
        try:
            idx = self.inputs.index(socket)
            return self.inputBinds[idx]
        except (ValueError, IndexError) as e:
            if isinstance(e, IndexError):
                easyError(f"{self.__class__.__name__}.getSlotKey: 未能找到输入绑定的槽键, 端口索引:{idx}")
            elif isinstance(e, ValueError):
                easyError(f"{self.__class__.__name__}.getSlotKey: 内部错误: {e}")
            return None

        

    def getSignalKeyBySocket(self, socket) -> str| None:
        idx = None
        try:
            idx = self.outputs.index(socket)
            return self.outputBinds[idx]
        except (ValueError, IndexError) as e:
            if isinstance(e, IndexError):
                easyError(f"{self.__class__.__name__}.getSignalKey: 未能找到输出绑定的信号键, 端口索引:{idx}")
            elif isinstance(e, ValueError):
                easyError(f"{self.__class__.__name__}.getSignalKey: 内部错误: {e}")
            return None

    def getSlot(self, key) -> "function":
        return self._slots.get(key, None)

    def getSignal(self, key) -> "pyqtSignal":
        return self._signals.get(key, None)


    def serialize(self):
        res = super().serialize()
        res['tppath'] = self.__class__.tppath
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        return res