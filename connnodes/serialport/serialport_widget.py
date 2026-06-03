from PyQt5.QtWidgets import QComboBox, QInputDialog
from PyQt5.QtSerialPort import QSerialPort, QSerialPortInfo
from PyQt5.QtCore import Qt, QByteArray, QObject, pyqtSlot, QMetaObject, QThread
from PyQt5.QtGui import QIcon, QPixmap

from .serialport import SerialPort
from .serialport_ui import Ui_SerialPort
from conn_utils import easyInfo, easyError, easyWarning, ThreadManager, disconnectAll
from conn_base import ConnNodeContentWidget


BAUD_RATE_ENUM = {
    "自定义": 0,
    "110": 110,
    "300": 300,
    "600": 600,
    "1200": 1200,
    "2400": 2400,
    "4800": 4800,
    "9600": 9600,
    "14400": 14400,
    "19200": 19200,
    "38400": 38400,
    "43000": 43000,
    "57600": 57600,
    "76800": 76800,
    "115200": 115200,
    "128000": 128000,
    "230400": 230400,
    "256000": 256000,
    "460800": 460800,
    "921600": 921600,
    "1000000": 1000000,
    "2000000": 2000000,
    "3000000": 3000000
}

DATA_BITS_ENUM = {
    "8": QSerialPort.Data8,
    "7": QSerialPort.Data7,
    "6": QSerialPort.Data6,
    "5": QSerialPort.Data5
}

PARITY_ENUM = {
    "无": QSerialPort.NoParity,
    "奇": QSerialPort.OddParity,
    "偶": QSerialPort.EvenParity,
    "空": QSerialPort.SpaceParity,
    "标记": QSerialPort.MarkParity
}

STOP_BITS_ENUM = {
    "1": QSerialPort.OneStop,
    "1.5": QSerialPort.OneAndHalfStop,
    "2": QSerialPort.TwoStop
}

FLOWCONTROL_ENUM = {
    "无流控": QSerialPort.NoFlowControl,
    "硬件流控": QSerialPort.HardwareControl,
    "软件流控": QSerialPort.SoftwareControl,
}

DEFAULT_CONF = {
    "baud_rate": 115200,
    "data_bits": QSerialPort.Data8,
    "parity": QSerialPort.NoParity,
    "stop_bits": QSerialPort.OneStop,
    "flow_control": QSerialPort.NoFlowControl,
}

def _combo_findData(combo: QComboBox, data, auto_add: bool = True) -> int:
    count = combo.count()
    idx = combo.findData(data)

    if idx == -1 and auto_add:
        combo.addItem(str(data), data)
        idx = count

    return idx


class SerialPort_Widget(ConnNodeContentWidget):
    """
    避免在外部修改串口的配置, 应该由 UI 全权修改,
    因为在这里直接调用了 QSerialPort 的配置方法。
    """

    class _Worker(QObject):
        def __init__(self, parent = None):
            super().__init__(parent)
            self._isDataSourceInit = False
            self._dataSource: SerialPort = None

        @pyqtSlot()
        def initDataSource(self):
            if not self._isDataSourceInit:
                self._isDataSourceInit = True
                self._dataSource = SerialPort(self)


    def initUI(self):
        self.ui = Ui_SerialPort()
        self._dataSourceWorker = self.__class__._Worker()
        self._workerThread = QThread()
        self._workerThread.start()

        # 防线程被析构导致的无声崩溃
        ThreadManager.instance().register_thread(self._workerThread)

        self._dataSourceWorker.moveToThread(self._workerThread)
        QMetaObject.invokeMethod(self._dataSourceWorker, "initDataSource", Qt.BlockingQueuedConnection)
        self.dataSource: SerialPort = self._dataSourceWorker._dataSource
        
        self._setupUi()
        self._connect_init()

        self.dataSource.device.setBaudRate(DEFAULT_CONF["baud_rate"])
        self.dataSource.device.setDataBits(DEFAULT_CONF["data_bits"])
        self.dataSource.device.setParity(DEFAULT_CONF["parity"])
        self.dataSource.device.setStopBits(DEFAULT_CONF["stop_bits"])
        self.dataSource.device.setFlowControl(DEFAULT_CONF["flow_control"])

        
    def cleanup(self) -> None:
        self.dataSource.close()
        self._dataSourceWorker.deleteLater()
        self._workerThread.quit()
        self._workerThread.wait(3000)
        self._workerThread.deleteLater()

    def _setupUi(self) -> None:
        self.ui.setupUi(self)

        for name, value in BAUD_RATE_ENUM.items():
            self.ui.baudRateSelecter.addItem(name, value)
   
        for name, value in DATA_BITS_ENUM.items():
            self.ui.dataBitsSelecter.addItem(name, value)

        for name, value in PARITY_ENUM.items():
            self.ui.paritySelecter.addItem(name, value)
        
        for name, value in STOP_BITS_ENUM.items():
            self.ui.stopBitsSelecter.addItem(name, value)

        for name, value in FLOWCONTROL_ENUM.items():
            self.ui.flowControlSelecter.addItem(name, value)

        icon = QIcon("icons/refresh.png")
        self.ui.portNameRefreshBtn.setIcon(icon)

        icon1 = QIcon()
        icon1.addPixmap(QPixmap("icons/deactive.png"), QIcon.Normal, QIcon.Off)
        icon1.addPixmap(QPixmap("icons/active.png"), QIcon.Active, QIcon.On)
        self.ui.portOpenBtn.setIcon(icon1)
        self.ui.portOpenBtn.setCheckable(True)

        icon2 = QIcon()
        icon2.addPixmap(QPixmap("icons/danger.png"), QIcon.Normal, QIcon.Off)
        self.ui.dangerLabel.setIcon(icon2)

        self._update_portNameSelecter(None)

        # TODO 暂时没找到细致修改全局样式的方法, 这里先简单处理
        self.setStyleSheet("""
QComboBox {
    background-color: #202020;
    color: #e0e0e0;
}
                           
QComboBox QAbstractItemView {
    background-color: #202020; 
}
                           
QCheckBox {
    color: #e0e0e0;
}
""")



    def _connect_init(self) -> None:
        self.ui.portNameRefreshBtn.clicked.connect(self._update_portNameSelecter)

        self.ui.portOpenBtn.clicked.connect(self._portOpenBtnClickedHandler)
        self.dataSource.openChanged.connect(self._updatePortOpenBtn)

        self.ui.portNameSelecter.currentIndexChanged.connect(self._portNameSelecter_changed_handler)
        self.dataSource.portNameChanged.connect(self._update_portNameSelecter)

        self.ui.baudRateSelecter.currentIndexChanged.connect(self._baudRateSelecterChangedHandler)
        self.dataSource.device.baudRateChanged.connect(self._updateBaudRateSelecter)

        self.ui.dataBitsSelecter.currentIndexChanged.connect(self._dataBitsSelecterChangedHandler)
        self.dataSource.device.dataBitsChanged.connect(self._updateDataBitsSelecter)

        self.ui.paritySelecter.currentIndexChanged.connect(self._paritySelecterChangedHandler)
        self.dataSource.device.parityChanged.connect(self._updateParitySelecter)

        self.ui.stopBitsSelecter.currentIndexChanged.connect(self._stopBitsSelecterChangedHandler)
        self.dataSource.device.stopBitsChanged.connect(self._updateStopBitsSelecter)

        self.ui.flowControlSelecter.currentIndexChanged.connect(self._flowControlSelecterChangedHandler)
        self.dataSource.device.flowControlChanged.connect(self._updateFlowControlSelecter)

        self.ui.FC_DTRCheckBox.stateChanged.connect(self._FC_DTRCheckBoxChangedHandler)
        self.ui.FC_RTSCheckBox.stateChanged.connect(self._FC_RTSCheckBoxChangedHandler)

        self._infoLogBtnStateChangedHandler(self.ui.infoLogBtn.checkState())
        self.ui.infoLogBtn.stateChanged.connect(self._infoLogBtnStateChangedHandler)

        self._errorLogBtnStateChangedHandler(self.ui.errorLogBtn.checkState())
        self.ui.errorLogBtn.stateChanged.connect(self._errorLogBtnStateChangedHandler)


    def _portOpenBtnClickedHandler(self) -> None:
        state = self.ui.portOpenBtn.isChecked()
        if state:
            self.dataSource.open()
        else:
            self.dataSource.close()

    def _updatePortOpenBtn(self, state: bool) -> None:
        self.ui.portOpenBtn.blockSignals(True)
        self.ui.portOpenBtn.setChecked(state)
        self.ui.portOpenBtn.blockSignals(False)

    def _portNameSelecter_changed_handler(self, idx: int) -> None:
        port_name = self.ui.portNameSelecter.itemData(idx)
        self.dataSource.setPortName(port_name)

    def _update_portNameSelecter(self, value: str) -> None:
        self.ui.portNameSelecter.blockSignals(True)

        if not isinstance(value, str):
            value = self.ui.portNameSelecter.currentData()

        self.ui.portNameSelecter.clear()

        self.ui.portNameSelecter.addItem("None", None)
        for info in QSerialPortInfo.availablePorts():
            self.ui.portNameSelecter.addItem(f"{info.portName()} {info.description()}", info.portName())
   
        idx = _combo_findData(self.ui.portNameSelecter, value, True)
        self.ui.portNameSelecter.setCurrentIndex(idx)

        self.ui.portNameSelecter.blockSignals(False)


    def _baudRateSelecterChangedHandler(self, idx: int) -> None:
        baud_rate = self.ui.baudRateSelecter.itemData(idx)

        if baud_rate == 0:
            text, ok = QInputDialog.getText(None, "输入框", "请输入波特率 (整数):")
            if ok and text.isdigit():
                baud_rate = int(text)
            elif self.ui.warningLogBtn.isChecked():
                self._warning_handler("输入波特率无效")
                return
  
        self.dataSource.device.setBaudRate(baud_rate)

    def _updateBaudRateSelecter(self, value: int) -> None:
        self.ui.baudRateSelecter.blockSignals(True)
        idx = _combo_findData(self.ui.baudRateSelecter, value, auto_add=True)
        self.ui.baudRateSelecter.setCurrentIndex(idx)
        self.ui.baudRateSelecter.blockSignals(False)

    def _dataBitsSelecterChangedHandler(self, idx: int) -> None:
        data_bits = self.ui.dataBitsSelecter.itemData(idx)
        self.dataSource.device.setDataBits(data_bits)

    def _updateDataBitsSelecter(self, value: int) -> None:
        self.ui.dataBitsSelecter.blockSignals(True)
        idx = _combo_findData(self.ui.dataBitsSelecter, value, auto_add=True)
        if idx != -1:
            self.ui.dataBitsSelecter.setCurrentIndex(idx)
        elif self.ui.warningLogBtn.isChecked():
            self._warning_handler(f"更新失败: 未找到数据位 {value}")
        self.ui.dataBitsSelecter.blockSignals(False)

    def _paritySelecterChangedHandler(self, idx: int) -> None:
        parity = self.ui.paritySelecter.itemData(idx)
        self.dataSource.device.setParity(parity)

    def _updateParitySelecter(self, value: int) -> None:
        self.ui.paritySelecter.blockSignals(True)
        idx = _combo_findData(self.ui.paritySelecter, value, auto_add=False)
        if idx != -1:
            self.ui.paritySelecter.setCurrentIndex(idx)
        elif self.ui.warningLogBtn.isChecked():
            self._warning_handler(f"未找到校验位 {value}")
        self.ui.paritySelecter.blockSignals(False)

    def _stopBitsSelecterChangedHandler(self, idx: int) -> None:
        stop_bits = self.ui.stopBitsSelecter.itemData(idx)
        self.dataSource.device.setStopBits(stop_bits)

    def _updateStopBitsSelecter(self, value: int) -> None:
        self.ui.stopBitsSelecter.blockSignals(True)
        idx = _combo_findData(self.ui.stopBitsSelecter, value, auto_add=False)
        if idx != -1:
            self.ui.stopBitsSelecter.setCurrentIndex(idx)
        elif self.ui.warningLogBtn.isChecked():
            self._warning_handler(f"未找到停止位 {value}")
        self.ui.stopBitsSelecter.blockSignals(False)

    def _flowControlSelecterChangedHandler(self, idx: int) -> None:
        flow_control = self.ui.flowControlSelecter.itemData(idx)
        self.dataSource.device.setFlowControl(flow_control)

    def _updateFlowControlSelecter(self, value: int) -> None:
        self.ui.flowControlSelecter.blockSignals(True)
        idx = _combo_findData(self.ui.flowControlSelecter, value, auto_add=False)
        if idx != -1:
            self.ui.flowControlSelecter.setCurrentIndex(idx)
        elif self.ui.warningLogBtn.isChecked():
            self._warning_handler(f"未找到流控制 {value}")
        self.ui.flowControlSelecter.blockSignals(False)

    def _FC_DTRCheckBoxChangedHandler(self, state: int) -> None:
        if state == Qt.Checked:
            self.dataSource.device.setDataTerminalReady(True)
        else:
            self.dataSource.device.setDataTerminalReady(False)

    def _FC_RTSCheckBoxChangedHandler(self, state: int) -> None:
        if state == Qt.Checked:
            self.dataSource.device.setRequestToSend(True)
        else:
            self.dataSource.device.setRequestToSend(False)

    def _infoLogBtnStateChangedHandler(self, state: int) -> None:
        if state == Qt.Checked:
            self.dataSource.received.connect(self._simpleComDisplayReceived)
        else:
            disconnectAll(self.dataSource.received, self._simpleComDisplayReceived)

    def _errorLogBtnStateChangedHandler(self, state: int) -> None:
        if state == Qt.Checked:
            self.dataSource.device.errorOccurred.connect(self._errorHandler)
        else:
            disconnectAll(self.dataSource.device.errorOccurred, self._errorHandler)

    def _simpleComDisplayReceived(self, data: QByteArray) -> None:
        text = bytes(data).decode("utf-8", errors='ignore')  # 或 'replace'
        self._infoHandler(text)

    def _infoHandler(self, msg: str) -> None:
        easyInfo(f"{self.dataSource.device.portName()}: {msg}")

    def _errorHandler(self, error) -> None:
        """
        error 参数类型: QSerialPort.SerialPortError (枚举)
        例如: QSerialPort.SerialPortError.NoError, 
            QSerialPort.SerialPortError.PermissionError,
            QSerialPort.SerialPortError.DeviceNotFoundError 等
        """
        if error == QSerialPort.SerialPortError.NoError:
            return
        
        error_string = self.dataSource.device.errorString()
        easyError(f"{self.dataSource.device.portName()}: {error_string}")

    def _warning_handler(self, msg: str) -> None:
        easyWarning(f"{self.dataSource.device.portName()}: {msg}")