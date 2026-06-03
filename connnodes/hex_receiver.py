"""
Hex 接收器 — 接收 QByteArray 并以 Hex 字符串形式显示

显示格式: "AA 55 01 02 0A 0B ..."
支持最大行数控制和清除功能。

端口:
  - receivedData(QByteArray): 接收二进制数据并显示为 Hex
"""

from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QTextBrowser,
                              QSpinBox, QLabel, QPushButton)
from PyQt5.QtGui import QTextCursor
from PyQt5.QtCore import QByteArray

from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf, ConnNodeContentWidget


class HexReceiverContent(ConnNodeContentWidget):
    """Hex 接收器内容部件 — Hex 字符串显示 + 最大行数控制"""

    def initUI(self):
        layout = QVBoxLayout(self)

        # ── Hex 显示区 ──────────────────────────────────────
        self.hexBrowser = QTextBrowser(self)
        layout.addWidget(self.hexBrowser)

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
        self.clearBtn.clicked.connect(self.hexBrowser.clear)
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
        self.hexBrowser.document().setMaximumBlockCount(value)

    def receivedData(self, data: QByteArray):
        """接收 QByteArray → 格式化为 Hex 字符串显示"""
        hex_str = " ".join(f"{b:02X}" for b in bytes(data))
        if hex_str:
            self.hexBrowser.moveCursor(QTextCursor.MoveOperation.End)
            self.hexBrowser.insertPlainText(hex_str + "\n")

    def cleanup(self):
        ...


@register_node()
class HexReceiverNode(ConnNode):
    tppath = ("可视化", "Hex接收器")
    icon = "icons/receiver.png"
    name = "Hex接收器"
    tooltip = "接收 QByteArray 并以 Hex 字符串形式显示"
    conn_title = "Hex接收器"

    NodeContent_class = HexReceiverContent

    def __init__(self, scene):
        super().__init__(scene,
            slotsConf=[
                ConnSocketConf(
                    socketType=1,
                    key="receivedData",
                    tooltip="接收 QByteArray 并显示为 Hex 字符串",
                    name="数据",
                    argsType=(QByteArray,)
                ),
            ]
        )
        self.registerSlot("receivedData", self.content.receivedData)

    def serialize(self):
        res = super().serialize()
        res['max_line_count'] = self.content.maxLineSpinBox.value()
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        self.content.maxLineSpinBox.setValue(data.get('max_line_count', 0))
        return res
