"""
文本接收器 — 接收文本并显示在 QTextBrowser 中

继承自原 data_receiver.py，纯改名，功能不变。

端口:
  - receivedDataHandler(QByteArray): 接收 QByteArray 并解析为 UTF-8 文本
  - receivedTextHandler(str): 直接接收文本字符串
"""

from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QTextBrowser,
                              QSpinBox, QLabel, QPushButton)
from PyQt5.QtGui import QTextCursor
from PyQt5.QtCore import QByteArray

from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf, ConnNodeContentWidget


class TextReceiverContent(ConnNodeContentWidget):
    """文本接收器内容部件 — 文本显示 + 最大行数控制"""

    def initUI(self):
        layout = QVBoxLayout(self)

        # ── 文本显示区 ──────────────────────────────────────
        self.textBrowser = QTextBrowser(self)
        layout.addWidget(self.textBrowser)

        # ── 控制栏 ──────────────────────────────────────────
        control_row = QHBoxLayout()
        self.maxLineLabel = QLabel("最大行数: 无限", self)
        self.maxLineSpinBox = QSpinBox(self)
        self.maxLineSpinBox.setMinimum(0)
        self.maxLineSpinBox.setMaximum(9999)

        control_row.addWidget(self.maxLineLabel)
        control_row.addWidget(self.maxLineSpinBox)
        layout.addLayout(control_row)

        self.clearBtn = QPushButton("清除", self)
        self.clearBtn.clicked.connect(self.textBrowser.clear)
        layout.addWidget(self.clearBtn)

        # ── 信号连接 ────────────────────────────────────────
        self.maxLineSpinBox.valueChanged.connect(self._onMaxLineChanged)

        self.setStyleSheet("QLabel { color: #e0e0e0; }")
        self.resize(200, 200)

    def _onMaxLineChanged(self, value: int):
        if value == 0:
            self.maxLineLabel.setText("最大行数: 无限")
        else:
            self.maxLineLabel.setText(f"最大行数: {value}")
        self.textBrowser.document().setMaximumBlockCount(value)

    def receivedDataHandler(self, data: QByteArray):
        """接收 QByteArray → 解码为 UTF-8 文本"""
        text = bytes(data).decode("utf-8", errors='ignore')
        self.textBrowser.moveCursor(QTextCursor.MoveOperation.End)
        self.textBrowser.insertPlainText(text)

    def receivedTextHandler(self, text: str):
        """直接接收文本字符串"""
        self.textBrowser.moveCursor(QTextCursor.MoveOperation.End)
        self.textBrowser.insertPlainText(text)

    def cleanup(self):
        ...


@register_node()
class TextReceiverNode(ConnNode):
    tppath = ("可视化", "文本接收器")
    icon = "icons/receiver.png"
    name = "文本接收器"
    tooltip = "接收 QByteArray 或文本字符串并显示"
    conn_title = "文本接收器"

    NodeContent_class = TextReceiverContent

    def __init__(self, scene):
        super().__init__(scene,
            slotsConf=[
                ConnSocketConf(
                    socketType=1,
                    key="receivedDataHandler",
                    tooltip="接收 QByteArray 类型数据并解析为 utf-8 文本字符串",
                    name="数据",
                    argsType=(QByteArray,)
                ),
                ConnSocketConf(
                    socketType=1,
                    key="receivedTextHandler",
                    tooltip="接收文本字符串",
                    name="文本",
                    argsType=(str,)
                ),
            ]
        )
        self.registerSlot("receivedDataHandler", self.content.receivedDataHandler)
        self.registerSlot("receivedTextHandler", self.content.receivedTextHandler)

    def serialize(self):
        res = super().serialize()
        res['max_line_count'] = self.content.maxLineSpinBox.value()
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        self.content.maxLineSpinBox.setValue(data.get('max_line_count', 0))
        return res
