from PyQt5.QtCore import QObject, pyqtSignal, QByteArray
from PyQt5.QtNetwork import QTcpServer, QTcpSocket, QHostAddress, QAbstractSocket


class TcpServer(QObject):
    """
    TCP 服务端核心类，封装 QTcpServer。
    运行在工作线程中，所有信号自动跨线程投递。

    信号说明：
        received(QByteArray)         — 收到客户端数据（不携带 clientId，方便连到 DataReceiver）
        clientConnected(int, str)    — 新客户端连接 (clientId, "地址:端口")
        clientDisconnected(int)      — 客户端断开 (clientId)
        listeningChanged(bool)       — 监听状态变化
        errorOccurred(str)           — 错误信息
    """
    received = pyqtSignal(QByteArray)
    clientConnected = pyqtSignal(int, str)
    clientDisconnected = pyqtSignal(int)
    listeningChanged = pyqtSignal(bool)
    errorOccurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = QTcpServer(self)
        self.server.newConnection.connect(self._newConnectionHandler)
        self._clients: dict[int, QTcpSocket] = {}
        self._nextClientId = 1

    # ──────────────── 客户端连接管理 ────────────────

    def _newConnectionHandler(self):
        """处理新客户端连接"""
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            clientId = self._nextClientId
            self._nextClientId += 1
            self._clients[clientId] = socket

            clientAddr = f"{socket.peerAddress().toString()}:{socket.peerPort()}"

            self._bindClientSignals(socket, clientId)
            self.clientConnected.emit(clientId, clientAddr)

    def _bindClientSignals(self, socket: QTcpSocket, clientId: int):
        """绑定客户端套接字的信号（使用内部类包装以避免闭包引用问题）"""
        handler = _ClientHandler(self, socket, clientId)
        socket.readyRead.connect(handler.onReadyRead)
        socket.disconnected.connect(handler.onDisconnected)
        # 持有 handler 引用防止被 GC
        socket._clientHandler = handler

    # ──────────────── 服务端控制 ────────────────

    def start(self, host: str, port: int):
        """开始监听指定地址和端口"""
        if self.server.isListening():
            self.errorOccurred.emit("服务器已在监听中")
            return

        address = QHostAddress(host) if host else QHostAddress.Any
        if not address.toIPv4Address() and host not in ("", "0.0.0.0", "127.0.0.1", "localhost"):
            self.errorOccurred.emit(f"无效的主机地址: {host}")
            return

        result = self.server.listen(address, port)
        self.listeningChanged.emit(result)
        if result:
            self._nextClientId = 1
        else:
            self.errorOccurred.emit(f"监听失败: {self.server.errorString()}")

    def stop(self):
        """停止监听并断开所有客户端"""
        # 断开所有客户端
        for clientId, socket in list(self._clients.items()):
            socket.disconnectFromHost()
            if socket._clientHandler:
                try:
                    disconnectClientHandler(socket._clientHandler, socket)
                except (TypeError, RuntimeError):
                    pass
                socket._clientHandler = None
        self._clients.clear()

        if self.server.isListening():
            self.server.close()
            self.listeningChanged.emit(False)

    # ──────────────── 数据发送 ────────────────

    def sendToAll(self, data: QByteArray):
        """向所有已连接的客户端发送二进制数据"""
        stale = []
        for clientId, socket in self._clients.items():
            if socket.state() == QAbstractSocket.ConnectedState:
                socket.write(data)
            else:
                stale.append(clientId)

        for cid in stale:
            self._removeClient(cid)

    def sendToClient(self, clientId: int, data: QByteArray):
        """向指定客户端发送二进制数据"""
        socket = self._clients.get(clientId)
        if socket and socket.state() == QAbstractSocket.ConnectedState:
            socket.write(data)

    def sendTextToAll(self, text: str):
        """向所有客户端发送文本（UTF-8 编码）"""
        self.sendToAll(QByteArray(text.encode("utf-8")))

    def sendTextToClient(self, clientId: int, text: str):
        """向指定客户端发送文本"""
        self.sendToClient(clientId, QByteArray(text.encode("utf-8")))

    # ──────────────── 查询方法 ────────────────

    def isListening(self) -> bool:
        return self.server.isListening()

    def getClientCount(self) -> int:
        return len(self._clients)

    def getServerPort(self) -> int:
        return self.server.serverPort()

    def getClientIds(self) -> list[int]:
        return list(self._clients.keys())

    # ──────────────── 内部方法 ────────────────

    def _removeClient(self, clientId: int):
        """内部：从客户端列表中移除指定客户端"""
        if clientId in self._clients:
            socket = self._clients.pop(clientId)
            if socket._clientHandler:
                try:
                    disconnectClientHandler(socket._clientHandler, socket)
                except (TypeError, RuntimeError):
                    pass
                socket._clientHandler = None


class _ClientHandler(QObject):
    """
    客户端信号处理器。
    每个客户端 socket 拥有一个独立实例，解决闭包在 PyQt5 信号中的生命周期问题。
    """

    def __init__(self, server: TcpServer, socket: QTcpSocket, clientId: int):
        super().__init__(socket)
        self.server = server
        self.socket = socket
        self.clientId = clientId

    def onReadyRead(self):
        """读取客户端数据并转发到 server.received 信号"""
        data = self.socket.readAll()
        if data:
            self.server.received.emit(data)

    def onDisconnected(self):
        """客户端断开时的清理"""
        self.server.clientDisconnected.emit(self.clientId)
        self.server._removeClient(self.clientId)


def disconnectClientHandler(handler: _ClientHandler, socket: QTcpSocket):
    """断开 _ClientHandler 的所有信号连接"""
    try:
        socket.readyRead.disconnect(handler.onReadyRead)
    except (TypeError, RuntimeError):
        pass
    try:
        socket.disconnected.disconnect(handler.onDisconnected)
    except (TypeError, RuntimeError):
        pass
