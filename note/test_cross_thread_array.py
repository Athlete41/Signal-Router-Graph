# 文件名: test_cross_thread_array.py
# 功能: 测试跨线程投递数据时，是引用传递还是拷贝传递
# 环境: Python 3.10.11, PyQt5 5.15.9
#
# 设计:
#   发送者在主线程，接收者在工作线程。
#   1. 发送者打印原始数据，发射 5 个信号
#   2. 接收者收到数据，直接存对象引用，并打印
#   3. 主线程 sleep(1) 确保接收者处理完毕
#   4. 发送者修改原始数据，打印修改后状态
#   5. 发送者发射 sig_check → 接收者打印存储的数据
#      如果存储的值变了 → 引用传递；如果没变 → 拷贝传递

import sys
import time
import numpy as np
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot, Qt
from PyQt5.QtWidgets import QApplication


class Sender(QObject):
    sig_list  = pyqtSignal(list)
    sig_dict  = pyqtSignal(dict)
    sig_obj   = pyqtSignal(object)
    sig_check = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.data_list = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.data_np   = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)
        self.data_dict = {"a": 1, "b": 2, "c": [3, 4, 5]}


class Receiver(QObject):
    def __init__(self):
        super().__init__()
        self.stored = {}

    def _store(self, key, data):
        """直接存接收到的对象引用，不转换"""
        self.stored[key] = data
        tid = int(QThread.currentThreadId())
        print(f"  [Receiver:{tid:#010x}] 收到 {key:20s}  id={id(data):#x}  val={data}")

    @pyqtSlot(list)
    def on_list(self, data):
        self._store("sig_list→list", data)

    @pyqtSlot(dict)
    def on_dict(self, data):
        self._store("sig_dict→dict", data)

    @pyqtSlot(object)
    def on_obj(self, data):
        if isinstance(data, list):
            self._store("sig_obj→list", data)
        elif isinstance(data, np.ndarray):
            self._store("sig_obj→np", data)
        elif isinstance(data, dict):
            self._store("sig_obj→dict", data)

    @pyqtSlot()
    def check_stored(self):
        """打印所有存储的数据，看是否受主线程修改影响"""
        tid = int(QThread.currentThreadId())
        print(f"  [Receiver:{tid:#010x}] check_stored:")
        for key, data in self.stored.items():
            print(f"    {key:20s}  id={id(data):#x}  val={data}")


def run_scene(conn_type, label):
    print(f"=== {label} ===")
    tid_main = int(QThread.currentThreadId())

    sender = Sender()
    receiver = Receiver()

    thread = QThread()
    thread.start()
    receiver.moveToThread(thread)

    sender.sig_list.connect(receiver.on_list, conn_type)
    sender.sig_dict.connect(receiver.on_dict, conn_type)
    sender.sig_obj.connect(receiver.on_obj, conn_type)
    sender.sig_check.connect(receiver.check_stored, conn_type)

    # 1. 发送者打印原始数据并发射
    print(f"  [Sender:{tid_main:#010x}] 原始数据:")
    print(f"    list  id={id(sender.data_list):#x}  val={sender.data_list}")
    print(f"    np    id={id(sender.data_np):#x}  val={sender.data_np}")
    print(f"    dict  id={id(sender.data_dict):#x}  val={sender.data_dict}")

    sender.sig_list.emit(sender.data_list)
    sender.sig_obj.emit(sender.data_list)
    sender.sig_obj.emit(sender.data_np)
    sender.sig_obj.emit(sender.data_dict)
    sender.sig_dict.emit(sender.data_dict)

    # 3. 等接收者处理完
    time.sleep(1)

    # 4. 发送者修改原始数据
    print(f"  [Sender:{tid_main:#010x}] 修改后:")
    sender.data_list[0] = 999.0
    sender.data_list.append(888.0)
    sender.data_np[0] = 999.0
    sender.data_dict["a"] = 999
    sender.data_dict["d"] = "new_key"
    print(f"    list  id={id(sender.data_list):#x}  val={sender.data_list}")
    print(f"    np    id={id(sender.data_np):#x}  val={sender.data_np}")
    print(f"    dict  id={id(sender.data_dict):#x}  val={sender.data_dict}")

    # 5. 通知接收者打印存储的数据
    sender.sig_check.emit()
    time.sleep(0.3)
    app.processEvents()

    thread.quit()
    thread.wait(3000)
    print()


if __name__ == "__main__":
    app = QApplication([])
    print(f"主线程ID: {int(QThread.currentThreadId()):#010x}\n")

    run_scene(Qt.AutoConnection,           "跨线程 AutoConnection")
    run_scene(Qt.QueuedConnection,         "跨线程 QueuedConnection")
    run_scene(Qt.BlockingQueuedConnection, "跨线程 BlockingQueuedConnection")

    print("=" * 60)
    print("测试完成")
    sys.exit(0)
