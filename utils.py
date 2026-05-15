import logging
import logging.handlers
from pathlib import Path
import queue
import typing
import types


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




def disconnect_all(signal, slot=None):
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
    if isinstance(method, types.MethodType):
        instance = method.__self__
        return isinstance(instance, QObject)
    return False

if __name__ == "__main__":
    logger.error("这是一条错误日志", exc_info=True)
    listener.stop()