from PyQt5.QtCore import QObject, pyqtSignal, QByteArray
from PyQt5.QtNetwork import QTcpSocket, QAbstractSocket


class TcpClient(QObject):
    """
    TCP 客户端核心类，封装 QTcpSocket。
    运行在工作线程中，所有信号自动跨线程投递。
    """
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    received = pyqtSignal(QByteArray)
    errorOccurred = pyqtSignal(str)
    stateChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.socket = QTcpSocket(self)
        self.socket.readyRead.connect(self._readDispatch)
        self.socket.connected.connect(self._onSocketConnected)
        self.socket.disconnected.connect(self._onSocketDisconnected)
        self.socket.stateChanged.connect(self._onSocketStateChanged)
        self.socket.errorOccurred.connect(self._errorDispatch)

    # ── 信号转发槽函数 ──────────────────────────────────────

    def _onSocketConnected(self):
        """转发 connected 信号"""
        self.connected.emit()

    def _onSocketDisconnected(self):
        """转发 disconnected 信号"""
        self.disconnected.emit()

    def _onSocketStateChanged(self, state):
        """转发 stateChanged 信号（state 为 QAbstractSocket.SocketState 枚举）"""
        self.stateChanged.emit(int(state))

    # ── 数据处理 ────────────────────────────────────────────

    def _readDispatch(self):
        """读取所有可用数据并发射 received 信号"""
        data = self.socket.readAll()
        if data and self.socket.state() == QAbstractSocket.ConnectedState:
            self.received.emit(data)

    def _errorDispatch(self, error):
        """转发错误信息（error 参数为 QAbstractSocket.SocketError 枚举）"""
        if error != QAbstractSocket.RemoteHostClosedError:
            self.errorOccurred.emit(self.socket.errorString())

    def connectToHost(self, host: str, port: int):
        """连接到指定主机和端口"""
        if self.socket.state() == QAbstractSocket.UnconnectedState:
            self.socket.connectToHost(host, port)
        else:
            self.errorOccurred.emit(f"当前状态不允许连接: {self.getStateString()}")

    def disconnectFromHost(self):
        """断开当前连接"""
        if self.socket.state() != QAbstractSocket.UnconnectedState:
            self.socket.disconnectFromHost()

    def sendData(self, data: QByteArray):
        """发送二进制数据"""
        if self.socket.state() == QAbstractSocket.ConnectedState:
            self.socket.write(data)
            self.socket.flush()
        else:
            self.errorOccurred.emit("未连接到服务器，无法发送数据")

    def sendText(self, text: str):
        """发送文本（自动编码为 UTF-8）"""
        if self.socket.state() == QAbstractSocket.ConnectedState:
            self.socket.write(text.encode("utf-8"))
            self.socket.flush()
        else:
            self.errorOccurred.emit("未连接到服务器，无法发送数据")

    def isConnected(self) -> bool:
        return self.socket.state() == QAbstractSocket.ConnectedState

    def getStateString(self) -> str:
        state = self.socket.state()
        states = {
            QAbstractSocket.UnconnectedState: "未连接",
            QAbstractSocket.HostLookupState: "正在解析主机",
            QAbstractSocket.ConnectingState: "正在连接",
            QAbstractSocket.ConnectedState: "已连接",
            QAbstractSocket.BoundState: "已绑定",
            QAbstractSocket.ClosingState: "正在关闭",
            QAbstractSocket.ListeningState: "监听中",
        }
        return states.get(state, f"未知状态({state})")
