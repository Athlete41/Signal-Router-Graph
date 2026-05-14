import logging
import logging.handlers
from pathlib import Path
import queue


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
from qtpy.QtGui import QTextCursor

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
            self.newNotify.emit(f"[错误]: {msg}")

    def warning(self, msg: str) -> None:
        if LEVEL <= logging.WARNING:
            self.newNotify.emit(f"[警告]: {msg}")

    def debug(self, msg: str) -> None:
        if LEVEL <= logging.DEBUG:
            self.newNotify.emit(f"[调试]: {msg}")

    def msg(self, msg: str) -> None:
        self.newNotify.emit(msg)

class SimpleLoggerBrowser(QTextBrowser):
    def updateNewMsg(self, msg: str) -> None:
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.insertPlainText(msg + "\n")


if __name__ == "__main__":
    logger.error("这是一条错误日志", exc_info=True)
    listener.stop()