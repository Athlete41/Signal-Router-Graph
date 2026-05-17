from PyQt5.QtSerialPort import QSerialPort
from PyQt5.QtCore import QIODevice, QByteArray, pyqtSignal, QObject


class SerialPort(QObject):
    portNameChanged = pyqtSignal(str)
    received = pyqtSignal(QByteArray)
    openChanged = pyqtSignal(bool)
    def __init__(self, parent = None):
        super().__init__(parent)
        self.device = QSerialPort()
        self.device.setParent(self)
        self.device.readyRead.connect(self._read_dispatch)

    def _read_dispatch(self):
        data = self.device.readAll()
        if data and self.device.isOpen(): 
            self.received.emit(data)

    def isOpen(self) -> bool:
        return self.device.isOpen()

    def sendData(self, data: QByteArray):
        self.device.write(data)

    def sendText(self, text: str):
        self.device.write(text.encode("utf-8"))

    def open(self, mode: int = QIODevice.ReadWrite):
        """每次开启都将更新, 否则触发按钮将失去一致性"""
        state = True
        if not self.device.isOpen():
            state = self.device.open(mode)
        self.openChanged.emit(state)
    
    def close(self):
        """每次关闭都将更新, 否则触发按钮将失去一致性"""
        state = False
        if self.device.isOpen():
            self.device.close()
        self.openChanged.emit(state)

    def setPortName(self, portName: str) -> None:
        old_portName = self.device.portName()
        if old_portName != portName:
            self.close()
            self.device.setPortName(portName)
            self.portNameChanged.emit(portName)
            
        