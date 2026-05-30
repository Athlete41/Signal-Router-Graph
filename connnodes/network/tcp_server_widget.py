from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QPushButton, QCheckBox, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QByteArray, QObject, pyqtSlot, QMetaObject, QThread
from PyQt5.QtGui import QIcon, QPixmap

from .tcp_server_core import TcpServer
from conn_utils import easyInfo, easyError, easyWarning, ThreadManager, disconnectAll
from conn_base import ConnNodeContentWidget


class TcpServer_Widget(ConnNodeContentWidget):
    """
    TCP 服务端 UI 组件。
    采用 _Worker + QThread 多线程模式，TcpServer 在工作线程中运行。
    """

    class _Worker(QObject):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._isInit = False
            self._server: TcpServer = None

        @pyqtSlot()
        def initServer(self):
            """在工作线程中创建 TcpServer 实例"""
            if not self._isInit:
                self._isInit = True
                self._server = TcpServer(self)

    def initUI(self):
        """初始化 UI 和工作线程"""
        # --- 工作线程初始化（与 serialport 模式一致） ---
        self._worker = self.__class__._Worker()
        self._thread = QThread()
        self._thread.start()

        ThreadManager.instance().register_thread(self._thread)

        self._worker.moveToThread(self._thread)
        QMetaObject.invokeMethod(self._worker, "initServer", Qt.BlockingQueuedConnection)
        self.server: TcpServer = self._worker._server

        # --- UI 搭建 ---
        self._setupUi()
        self._connectSignals()

    def cleanup(self):
        """清理资源"""
        self.server.stop()
        self._worker.deleteLater()
        self._thread.quit()
        self._thread.wait(3000)
        self._thread.deleteLater()

    # ──────────────── UI 搭建 ────────────────

    def _setupUi(self):
        layout = QVBoxLayout(self)

        # 监听地址
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("监听"))
        self.hostInput = QLineEdit("0.0.0.0")
        self.hostInput.setPlaceholderText("0.0.0.0 = 所有接口")
        h1.addWidget(self.hostInput)
        layout.addLayout(h1)

        # 端口
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("端口"))
        self.portInput = QSpinBox()
        self.portInput.setRange(1, 65535)
        self.portInput.setValue(8080)
        h2.addWidget(self.portInput)
        layout.addLayout(h2)

        # 启动/停止按钮
        self.startBtn = QPushButton("启动")
        icon = QIcon()
        icon.addPixmap(QPixmap("icons/deactive.png"), QIcon.Normal, QIcon.Off)
        icon.addPixmap(QPixmap("icons/active.png"), QIcon.Active, QIcon.On)
        self.startBtn.setIcon(icon)
        self.startBtn.setCheckable(True)
        layout.addWidget(self.startBtn)

        # 状态标签
        self.statusLabel = QLabel("状态: 未监听")
        layout.addWidget(self.statusLabel)

        # 客户端数量
        self.clientCountLabel = QLabel("已连接客户端: 0")
        layout.addWidget(self.clientCountLabel)

        # 客户端列表
        self.clientList = QListWidget()
        self.clientList.setMaximumHeight(80)
        layout.addWidget(self.clientList)

        # 日志勾选框
        logLayout = QHBoxLayout()
        self.infoCb = QCheckBox("信息")
        self.infoCb.setChecked(True)
        self.warnCb = QCheckBox("警告")
        self.warnCb.setChecked(True)
        self.errCb = QCheckBox("错误")
        self.errCb.setChecked(True)
        logLayout.addWidget(self.infoCb)
        logLayout.addWidget(self.warnCb)
        logLayout.addWidget(self.errCb)
        layout.addLayout(logLayout)

        # 样式
        self.setStyleSheet("""
            QLineEdit, QSpinBox, QListWidget {
                background-color: #202020;
                color: #e0e0e0;
            }
            QCheckBox, QLabel {
                color: #e0e0e0;
            }
        """)

    # ──────────────── 信号连接 ────────────────

    def _connectSignals(self):
        self.startBtn.clicked.connect(self._onStartBtnClicked)

        self.server.listeningChanged.connect(self._onListeningChanged)
        self.server.clientConnected.connect(self._onClientConnected)
        self.server.clientDisconnected.connect(self._onClientDisconnected)

        self.infoCb.stateChanged.connect(self._onInfoCbChanged)
        self.warnCb.stateChanged.connect(self._onWarnCbChanged)
        self.errCb.stateChanged.connect(self._onErrCbChanged)

        # 初始状态
        self._onInfoCbChanged(self.infoCb.checkState())
        self._onWarnCbChanged(self.warnCb.checkState())
        self._onErrCbChanged(self.errCb.checkState())

    # ──────────────── 事件处理 ────────────────

    def _onStartBtnClicked(self):
        if self.startBtn.isChecked():
            host = self.hostInput.text().strip()
            port = self.portInput.value()
            self.server.start(host, port)
        else:
            self.server.stop()

    def _onListeningChanged(self, success: bool):
        self.startBtn.blockSignals(True)
        self.startBtn.setChecked(success)
        self.startBtn.blockSignals(False)

        if success:
            self.startBtn.setText("停止")
            self.statusLabel.setText(f"状态: 监听中 (端口 {self.server.getServerPort()})")
            easyInfo(f"TCP服务端: 已启动，监听端口 {self.server.getServerPort()}")
        else:
            self.startBtn.setText("启动")
            self.statusLabel.setText("状态: 未监听")

    def _onClientConnected(self, clientId: int, address: str):
        self._updateClientCount()
        text = f"[{clientId}] {address}"
        self.clientList.addItem(text)
        easyInfo(f"TCP服务端: 客户端 {address} 已连接 (ID={clientId})")

    def _onClientDisconnected(self, clientId: int):
        self._updateClientCount()
        for i in range(self.clientList.count()):
            item = self.clientList.item(i)
            if item and item.text().startswith(f"[{clientId}]"):
                self.clientList.takeItem(i)
                break
        easyInfo(f"TCP服务端: 客户端 ID={clientId} 已断开")

    def _updateClientCount(self):
        count = self.server.getClientCount()
        self.clientCountLabel.setText(f"已连接客户端: {count}")

    # ──────────────── 日志控制 ────────────────

    def _onInfoCbChanged(self, state):
        if state == Qt.Checked:
            self.server.received.connect(self._infoHandler)
        else:
            disconnectAll(self.server.received, self._infoHandler)

    def _onWarnCbChanged(self, state):
        if state == Qt.Checked:
            self.server.clientConnected.connect(self._warnConnHandler)
        else:
            disconnectAll(self.server.clientConnected, self._warnConnHandler)

    def _onErrCbChanged(self, state):
        if state == Qt.Checked:
            self.server.errorOccurred.connect(self._errHandler)
        else:
            disconnectAll(self.server.errorOccurred, self._errHandler)

    def _infoHandler(self, data: QByteArray):
        text = bytes(data).decode("utf-8", errors="replace")
        easyInfo(f"TCP服务端 收到: {text}")

    def _warnConnHandler(self, clientId: int, address: str):
        pass  # 连接事件的日志已在 _onClientConnected 中处理

    def _errHandler(self, msg: str):
        easyError(f"TCP服务端 错误: {msg}")
