from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QPushButton, QCheckBox
from PyQt5.QtCore import Qt, QByteArray, QObject, pyqtSlot, QMetaObject, QThread
from PyQt5.QtGui import QIcon, QPixmap

from .tcp_client_core import TcpClient
from conn_utils import easyInfo, easyError, easyWarning, ThreadManager, disconnectAll
from conn_base import ConnNodeContentWidget


class TcpClient_Widget(ConnNodeContentWidget):
    """
    TCP 客户端 UI 组件。
    采用 _Worker + QThread 多线程模式，TcpClient 在工作线程中运行。
    """

    class _Worker(QObject):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._isInit = False
            self._client: TcpClient = None

        @pyqtSlot()
        def initClient(self):
            """在工作线程中创建 TcpClient 实例"""
            if not self._isInit:
                self._isInit = True
                self._client = TcpClient(self)

    def initUI(self):
        """初始化 UI 和工作线程"""
        # --- 工作线程初始化（与 serialport 模式一致） ---
        self._worker = self.__class__._Worker()
        self._thread = QThread()
        self._thread.start()

        ThreadManager.instance().register_thread(self._thread)

        self._worker.moveToThread(self._thread)
        QMetaObject.invokeMethod(self._worker, "initClient", Qt.BlockingQueuedConnection)
        self.client: TcpClient = self._worker._client

        # --- UI 搭建 ---
        self._setupUi()
        self._connectSignals()

    def cleanup(self):
        """清理资源"""
        self.client.disconnectFromHost()
        self._worker.deleteLater()
        self._thread.quit()
        self._thread.wait(3000)
        self._thread.deleteLater()

    # ──────────────── UI 搭建 ────────────────

    def _setupUi(self):
        layout = QVBoxLayout(self)

        # 主机地址
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("主机"))
        self.hostInput = QLineEdit("127.0.0.1")
        self.hostInput.setPlaceholderText("IP 地址或域名")
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

        # 连接按钮
        self.connectBtn = QPushButton("连接")
        icon = QIcon()
        icon.addPixmap(QPixmap("icons/deactive.png"), QIcon.Normal, QIcon.Off)
        icon.addPixmap(QPixmap("icons/active.png"), QIcon.Active, QIcon.On)
        self.connectBtn.setIcon(icon)
        self.connectBtn.setCheckable(True)
        layout.addWidget(self.connectBtn)

        # 状态标签
        self.statusLabel = QLabel("状态: 未连接")
        layout.addWidget(self.statusLabel)

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
            QLineEdit, QSpinBox {
                background-color: #202020;
                color: #e0e0e0;
            }
            QCheckBox, QLabel {
                color: #e0e0e0;
            }
        """)

    # ──────────────── 信号连接 ────────────────

    def _connectSignals(self):
        self.connectBtn.clicked.connect(self._onConnectBtnClicked)

        self.client.connected.connect(self._onConnected)
        self.client.disconnected.connect(self._onDisconnected)
        self.client.stateChanged.connect(self._onStateChanged)

        self.infoCb.stateChanged.connect(self._onInfoCbChanged)
        self.warnCb.stateChanged.connect(self._onWarnCbChanged)
        self.errCb.stateChanged.connect(self._onErrCbChanged)

        # 初始状态
        self._onInfoCbChanged(self.infoCb.checkState())
        self._onWarnCbChanged(self.warnCb.checkState())
        self._onErrCbChanged(self.errCb.checkState())

    # ──────────────── 事件处理 ────────────────

    def _onConnectBtnClicked(self):
        if self.connectBtn.isChecked():
            host = self.hostInput.text().strip()
            if not host:
                easyWarning("TCP客户端: 主机地址不能为空")
                self.connectBtn.blockSignals(True)
                self.connectBtn.setChecked(False)
                self.connectBtn.blockSignals(False)
                return
            port = self.portInput.value()
            self.client.connectToHost(host, port)
        else:
            self.client.disconnectFromHost()

    def _onConnected(self):
        """连接成功时更新按钮状态"""
        self.connectBtn.blockSignals(True)
        self.connectBtn.setChecked(True)
        self.connectBtn.blockSignals(False)
        self.connectBtn.setText("断开")
        self._updateStatus()
        easyInfo("TCP客户端: 已连接")

    def _onDisconnected(self):
        """断开连接时更新按钮状态"""
        self.connectBtn.blockSignals(True)
        self.connectBtn.setChecked(False)
        self.connectBtn.blockSignals(False)
        self.connectBtn.setText("连接")
        self._updateStatus()
        easyInfo("TCP客户端: 已断开")

    def _onStateChanged(self, state):
        self._updateStatus()

    def _updateStatus(self):
        self.statusLabel.setText(f"状态: {self.client.getStateString()}")

    # ──────────────── 日志控制 ────────────────

    def _onInfoCbChanged(self, state):
        if state == Qt.Checked:
            self.client.received.connect(self._infoHandler)
        else:
            disconnectAll(self.client.received, self._infoHandler)

    def _onWarnCbChanged(self, state):
        if state == Qt.Checked:
            self.client.disconnected.connect(self._warnHandler)
        else:
            disconnectAll(self.client.disconnected, self._warnHandler)

    def _onErrCbChanged(self, state):
        if state == Qt.Checked:
            self.client.errorOccurred.connect(self._errHandler)
            self.client.connected.connect(self._clearErrHandler)
        else:
            disconnectAll(self.client.errorOccurred, self._errHandler)
            disconnectAll(self.client.connected, self._clearErrHandler)

    def _infoHandler(self, data: QByteArray):
        text = bytes(data).decode("utf-8", errors="replace")
        easyInfo(f"TCP客户端 收到: {text}")

    def _warnHandler(self):
        easyWarning("TCP客户端: 连接已断开")

    def _errHandler(self, msg: str):
        easyError(f"TCP客户端 错误: {msg}")

    def _clearErrHandler(self):
        pass  # 连接成功后清除错误状态的占位
