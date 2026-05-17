from qtpy.QtGui import QImage
from qtpy.QtCore import Qt
from qtpy.QtGui import QFont, QFontMetrics

from nodeeditor.node_socket import Socket
from nodeeditor.node_graphics_socket import QDMGraphicsSocket
from nodeeditor.node_node import Node
from nodeeditor.node_graphics_node import QDMGraphicsNode
from nodeeditor.node_socket import LEFT_CENTER, RIGHT_CENTER, LEFT_BOTTOM, LEFT_TOP, RIGHT_BOTTOM, RIGHT_TOP
from conn_utils import easyInfo, easyError, easyWarning, easyDebug, easyMsg, isRealSignal, isQObjectInstanceMethod, disconnectAll
from conn_conf import GlobalSettingManager

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

    # def paint(self, painter, QStyleOptionGraphicsItem, widget=None):
    #     super().paint(painter, QStyleOptionGraphicsItem, widget)

    #     offset = 24.0
    #     if self.node.isDirty(): offset = 0.0
    #     if self.node.isInvalid(): offset = 48.0

    #     painter.drawImage(
    #         QRectF(-10, -10, 24.0, 24.0),
    #         self.icons,
    #         QRectF(offset, 0, 24.0, 24.0)
    #     )

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
                 ):
        if not isinstance(key, str) or key.strip() == "":
            raise TypeError("key 必须是非空字符串")
        
        self.socketType = socketType
        self.key = key
        self.tooltip = tooltip
        self.name = name

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



class ConnNode(Node):
    tppath = None
    icon = ""
    name = "未定义的名称"
    tooltip = "未定义的提示"
    conn_title = "未定义的标题"

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
                self.outputs[idx].setToolTip(conf.tooltip if conf.tooltip else "")
                self.outputs[idx].setText(conf.name if conf.name else conf.key)

            for idx, conf in enumerate(slotsConf):
                self.inputs[idx].setToolTip(conf.tooltip if conf.tooltip else "")
                self.inputs[idx].setText(conf.name if conf.name else conf.key)

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

        # 运行多个输入
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
            output_socket = start_socket if start_socket.is_output else end_socket
            input_socket = end_socket if start_socket.is_output else start_socket
            if output_socket.node is not self:
                return
            
            signal_owner = None
            signal_key = None
            slot_owner = None
            slot_key = None
            try:
                signal_owner = output_socket.node
                signal_key = self.getSignalKeyBySocket(output_socket)
                slot_owner = input_socket.node
                slot_key = input_socket.node.getSlotKeyBySocket(input_socket)
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
        return self._slots.get(key)

    def getSignal(self, key) -> "pyqtSignal":
        return self._signals.get(key)

    def serialize(self):
        res = super().serialize()
        res['tppath'] = self.__class__.tppath
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        return res