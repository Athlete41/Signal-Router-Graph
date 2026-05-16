# 文件名: test_emit.py
# 功能: 测试跨线程下 emit 的投递策略
# 环境: Python 3.10.11, PyQt5 5.15.9
# 控制流-1: 按钮1 --> 主线程代理 --> 工作信号 --> 工作函数
# 代理在主线程持有工作信号并发送
# 控制流-2: 按钮2 --> 工作线程代理 --> 工作信号 --> 工作函数
# 代理在工作线程持有工作信号并发送
# 控制流-3: 按钮3 --> 子线程代理 --> 工作信号 --> 工作函数
# 代理在子线程持有工作信号并发送

# 工作信号与工作函数会在牛马移动前进行连接, 移动后再次连接。


from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtBoundSignal, Qt
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton
import sys

class Proxy(QObject):
    upsig = pyqtSignal()

    def __init__(self, name: str, finalsig: pyqtBoundSignal):
        super().__init__()
        self.name = name
        self.finalsig = finalsig

    def proxy_send(self):
        print(f"{self.name}: 传递任务, 线程ID: {int(QThread.currentThreadId())}")
        self.finalsig.emit()

class Slave(QObject):
    work_sig = pyqtSignal()

    def _work_by_AutoConnection_before(self):
        print(f"牛马: 我完成了工作! 连接时机: 移动前, 连接类型: Auto, 线程ID: {int(QThread.currentThreadId())}")

    def _work_by_AutoConnection_after(self):
        print(f"牛马: 我完成了工作! 连接时机: 移动后, 连接类型: Auto, 线程ID: {int(QThread.currentThreadId())}")

    def _work_by_DirectConnection_before(self):
        print(f"牛马: 我完成了工作! 连接时机: 移动前, 连接类型: Direct, 线程ID: {int(QThread.currentThreadId())}")

    def _work_by_DirectConnection_after(self):
        print(f"牛马: 我完成了工作! 连接时机: 移动后, 连接类型: Direct, 线程ID: {int(QThread.currentThreadId())}")

    def _work_by_QueuedConnection_before(self):
        print(f"牛马: 我完成了工作! 连接时机: 移动前, 连接类型: Queued, 线程ID: {int(QThread.currentThreadId())}")

    def _work_by_QueuedConnection_after(self):
        print(f"牛马: 我完成了工作! 连接时机: 移动后, 连接类型: Queued, 线程ID: {int(QThread.currentThreadId())}")

    def _work_by_BlockingQueuedConnection_before(self):
        print(f"牛马: 我完成了工作! 连接时机: 移动前, 连接类型: BlockingQueued, 线程ID: {int(QThread.currentThreadId())}")

    def _work_by_BlockingQueuedConnection_after(self):
        print(f"牛马: 我完成了工作! 连接时机: 移动后, 连接类型: BlockingQueued, 线程ID: {int(QThread.currentThreadId())}")


class Boss(QWidget):
    def __init__(self):
        super().__init__()
        Layout = QVBoxLayout(self)
        self.mission_cmd_main = QPushButton("发布任务-通过主线程代理", self)
        self.mission_cmd_work = QPushButton("发布任务-通过工作线程代理", self)
        self.mission_cmd_sub = QPushButton("发布任务-通过子线程代理", self)

        Layout.addWidget(self.mission_cmd_main)
        Layout.addWidget(self.mission_cmd_work)
        Layout.addWidget(self.mission_cmd_sub)
        self.setFixedHeight(200)
        self.setFixedWidth(200)


app = QApplication([])
MAIN_THREAD_ID = int(QThread.currentThreadId())
print(f"主线程ID: {MAIN_THREAD_ID}")

work_thread = QThread()
work_thread.start()

sub_thread = QThread()
sub_thread.start()

boss = Boss()
slave = Slave()
proxy_main = Proxy("主线程代理", slave.work_sig)
boss.mission_cmd_main.clicked.connect(proxy_main.proxy_send)

proxy_work = Proxy("工作线程代理", slave.work_sig)
proxy_work.moveToThread(work_thread)
boss.mission_cmd_work.clicked.connect(proxy_work.proxy_send)

proxy_sub = Proxy("子线程代理", slave.work_sig)
proxy_sub.moveToThread(sub_thread)
boss.mission_cmd_sub.clicked.connect(proxy_sub.proxy_send)



slave.work_sig.connect(slave._work_by_AutoConnection_before, Qt.AutoConnection)
slave.work_sig.connect(slave._work_by_DirectConnection_before, Qt.DirectConnection)
slave.work_sig.connect(slave._work_by_QueuedConnection_before, Qt.QueuedConnection)
slave.work_sig.connect(slave._work_by_BlockingQueuedConnection_before, Qt.BlockingQueuedConnection) # 会导致死锁
slave.moveToThread(work_thread)
slave.work_sig.connect(slave._work_by_AutoConnection_after, Qt.AutoConnection)
slave.work_sig.connect(slave._work_by_DirectConnection_after, Qt.DirectConnection)
slave.work_sig.connect(slave._work_by_QueuedConnection_after, Qt.QueuedConnection)
slave.work_sig.connect(slave._work_by_BlockingQueuedConnection_after, Qt.BlockingQueuedConnection) # 会导致死锁

boss.show()

sys.exit(app.exec_())



# 结论: https://blog.csdn.net/Athlete41/article/details/160889770

# 执行信号投递的线程	连接类型	回调对象当前的线程	回调对象连接那一刻的线程	消费线程
# 主线程	Auto	工作线程	主线程	主线程
# 主线程	Auto	工作线程	工作线程	工作线程
# 主线程	Queued	工作线程	主线程	主线程
# 主线程	Queued	工作线程	工作线程	工作线程
# 主线程	Direct	工作线程	主线程	主线程
# 主线程	Direct	工作线程	工作线程	主线程
# ----------------------	----------	---------------------	--------------------------	----------
# 工作线程	Auto	工作线程	主线程	主线程
# 工作线程	Auto	工作线程	工作线程	工作线程
# 工作线程	Queued	工作线程	主线程	主线程
# 工作线程	Queued	工作线程	工作线程	工作线程
# 工作线程	Direct	工作线程	主线程	工作线程
# 工作线程	Direct	工作线程	工作线程	工作线程
# ----------------------	----------	---------------------	--------------------------	----------
# 子线程	Auto	工作线程	主线程	主线程
# 子线程	Auto	工作线程	工作线程	工作线程
# 子线程	Queued	工作线程	主线程	主线程
# 子线程	Queued	工作线程	工作线程	工作线程
# 子线程	Direct	工作线程	主线程	子线程
# 子线程	Direct	工作线程	工作线程	子线程

# Auto 类型
# OK, 可以开始分析了，首先关注 Qt.AutoConnection，很明显: 消费线程 = 回调对象连接那一刻的线程 。
# 说明它有某种快照机制。

# 具体流，结合官方文档，应该是这样:
# 比较-相同 --> 同步执行
# 比较-不同 --> 异步执行

# signal.connect(slot, Qt.AutoConnection)执行的那一刻生成了slot所属对象的线程快照，后续调用signal.emit的时候会对emit的执行线程与快照线程进行比较，如果是相同则直接同步调用(嵌套), 否则异步，使用调试器能清楚观察到，这里不详细展开。

# Queued 类型
# 接下是 Qt.QueuedConnection，从表上看很明显与 Auto 类型一样有快照机制: 消费线程 = 回调对象连接那一刻的线程 。

# 具体流，结合官方文档:
# 强制异步

# 与Auto一样有快照，不过不比较快照，只是根据快照决定投递到哪里，强制异步，使用调试器能追踪。

# Direct 类型
# 关于Qt.DirectConnection，这与前两者不一样，不过也很明显: 消费线程 = 信号投递时所处的线程

# 具体流，结合官方文档:
# 强制同步
