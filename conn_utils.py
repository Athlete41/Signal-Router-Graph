import logging
import logging.handlers
from pathlib import Path
import queue
import typing


LEVEL = logging.DEBUG

def _setup_logger(path: Path):
    log_file = path
    
    log_queue = queue.Queue(-1)
    
    queue_handler = logging.handlers.QueueHandler(log_queue)
    queue_handler.setLevel(LEVEL)
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    stream_handler = logging.StreamHandler()
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    
    listener = logging.handlers.QueueListener(log_queue, file_handler, stream_handler)
    listener.start()
    
    root_logger = logging.getLogger()
    root_logger.addHandler(queue_handler)
    root_logger.setLevel(LEVEL)
    

    return logging.getLogger("ConnGraph"), listener


log_file = Path(__file__).parent.parent / "app.log"
logger, listener = _setup_logger(log_file)

from PyQt5.QtCore import QObject, pyqtSignal
from qtpy.QtWidgets import QTextBrowser

class SimpleLogger(QObject):
    """
    简单日志记录器 (全局单例，长期存活)
    """
    newNotify = pyqtSignal(str)
    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)

    def info(self, msg: str) -> None:
        if LEVEL <= logging.INFO:
            self.newNotify.emit(f"[消息]: {msg}")

    def error(self, msg: str) -> None:
        if LEVEL <= logging.ERROR:
            self.newNotify.emit(f"<span style=\"color: red;\">[错误]: {msg}</span>")

    def warning(self, msg: str) -> None:
        if LEVEL <= logging.WARNING:
            self.newNotify.emit(f"<span style=\"color: orange;\">[警告]: {msg}</span>")

    def debug(self, msg: str) -> None:
        if LEVEL <= logging.DEBUG:
            self.newNotify.emit(f"<span style=\"color: lightgreen;\">[调试]: {msg}</span>")

    def msg(self, msg: str) -> None:
        self.newNotify.emit(msg)

class SimpleLoggerBrowser(QTextBrowser):
    def updateNewMsg(self, msg: str) -> None:
        self.append(msg)

def easyInfo(msg: str) -> None:
    SimpleLogger.instance().info(msg)
    logger.info(msg)

def easyError(msg: typing.Union[str, Exception])  -> None:
    SimpleLogger.instance().error(msg)
    if isinstance(msg, Exception):
        logger.error(msg, exc_info=True)
    else:
        logger.error(msg)

def easyWarning(msg: str) -> None:
    SimpleLogger.instance().warning(msg)
    logger.warning(msg)

def easyDebug(msg: str) -> None:
    SimpleLogger.instance().debug(msg)
    logger.debug(msg)

def easyMsg(msg: str) -> None:
    SimpleLogger.instance().msg(msg)




def disconnectAll(signal, slot=None):
    """基于 PyQt5.15.9 版本"""
    depth = 0
    if slot is not None:
        while True:
            try:
                signal.disconnect(slot)
            except TypeError:
                break

            # 一般不可能
            depth += 1
            if depth > 100: 
                easyWarning("深度超过100! 检测 Qt 是否为 PyQt5.15.9 版本")
                break
    else:
        signal.disconnect()


def isRealSignal(obj):
    return callable(getattr(obj, 'connect')) and callable(getattr(obj, 'disconnect')) and callable(getattr(obj, 'emit'))

def isQObjectInstanceMethod(method):
    return hasattr(method, '__self__') and isinstance(method.__self__, QObject)


from PyQt5.QtCore import QObject, QThread, QMutex, QMutexLocker, pyqtSignal, QTimer
from PyQt5.sip import isdeleted
import typing


class ThreadManager(QObject):
    """
    线程管理器 (全局单例，长期存活)
    持有线程强引用，确保不会被意外析构。
    提供线程注册/注销接口，自动监听 finished 信号并从列表中移除。
    提供 shutdown_all_threads 用于程序退出时统一停止所有线程。
    """
    list_changed_notify = pyqtSignal()

    _instance = None
    _mutex = QMutex()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self._threads: list[QThread] = []   # 存储所有注册的线程（强引用）
        # 定时轮询清理（兜底，防止 finished 信号丢失）
        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.setInterval(5000)
        self._cleanup_timer.timeout.connect(self._clean_dead_threads)
        self._cleanup_timer.start()

    def register_thread(self, thread: typing.Union[QThread, None]):
        """
        注册一个线程，管理器将持有其强引用。
        线程结束时（finished 信号）会自动注销。
        """
        if not isinstance(thread, QThread) and thread is not None:
            raise TypeError("必须是 QThread 实例或 None 类型")
        if isdeleted(thread):
            raise ValueError("线程对象已被删除")

        with QMutexLocker(self._mutex):
            if thread in self._threads:
                return
            self._threads.append(thread)

        thread.finished.connect(self._auto_unregister)
        self._broadcast_list_changed()

    def unregister_thread(self, thread: QThread):
        """手动注销一个线程，不再管理"""
        with QMutexLocker(self._mutex):
            if thread not in self._threads:
                return
            self._threads.remove(thread)

        try:
            disconnectAll(thread.finished, self._auto_unregister)
        except (TypeError, RuntimeError):
            pass
        self._broadcast_list_changed()

    def _auto_unregister(self):
        """由 finished 信号触发，自动注销发出信号的线程"""
        thread = self.sender()
        if thread is None or isdeleted(thread):
            return
        # 调用 unregister_thread 会再次加锁，但这里锁已经释放，安全
        self.unregister_thread(thread)

    def _clean_dead_threads(self):
        """定时器轮询清理"""
        to_remove = []
        with QMutexLocker(self._mutex):
            for thread in self._threads:
                if isdeleted(thread):
                    to_remove.append(thread)
            for thread in to_remove:
                self._threads.remove(thread)
        if to_remove:
            self._broadcast_list_changed()

    def shutdown_all_threads(self, timeout_ms: int = 1000):
        with QMutexLocker(self._mutex):
            threads_copy = self._threads.copy()
        for thread in threads_copy:
            if thread.isRunning():
                thread.quit()
                thread.wait(timeout_ms)

    def get_list(self) -> list[QThread]:
        with QMutexLocker(self._mutex):
            return self._threads.copy()

    def get_count(self) -> int:
        with QMutexLocker(self._mutex):
            return len(self._threads)

    def _broadcast_list_changed(self):
        self.list_changed_notify.emit()




if __name__ == "__main__":
    logger.error("这是一条错误日志", exc_info=True)
    listener.stop()