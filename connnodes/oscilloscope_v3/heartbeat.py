"""
HeartbeatWidget — 通过 paintEvent 计数检测实际可视性

挂载到待监测控件的父级下，定时器通过比较 beat_count 判断 paintEvent 是否还在触发。
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPaintEvent


class HeartbeatWidget(QWidget):
    """心跳控件：paintEvent 只做计数，不画任何东西"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.beat_count = 0
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event: QPaintEvent) -> None:
        self.beat_count += 1
