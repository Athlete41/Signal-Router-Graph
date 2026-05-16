# 文件名: test_disconnect.py
# 功能: 测试断开信号连接, 实际上 disconnect(callback) 可能有非预期的行为, 一次只能断开一个连接并且LIFO
# 环境: Python 3.10.11, PyQt5 5.15.9

from PyQt5.QtCore import QObject, pyqtSignal, Qt
from PyQt5.QtWidgets import QApplication
import sys

class Sender(QObject):
    sig = pyqtSignal()

    def slot(self):
        print("slot called")

sender = Sender()

# conn1 = sender.sig.connect(sender.slot, Qt.QueuedConnection)
conn1 = sender.sig.connect(sender.slot, Qt.AutoConnection)
conn2 = sender.sig.connect(sender.slot, Qt.AutoConnection)

app = QApplication([])


print("两次连接后，发出信号：")
sender.sig.emit()

sender.sig.disconnect(sender.slot)

print("断开后，发出信号：")
sender.sig.emit()

sys.exit(app.exec_())
