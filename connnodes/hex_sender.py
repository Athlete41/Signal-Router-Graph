"""
Hex 发送器 — Hex 编辑 + 二进制文件加载 + 定时器发送

功能:
  - 多行 Hex 编辑区（如 "AA 55 01 02\\n0A 0B"）
  - 加载 .bin 文件显示为 Hex 字符串
  - 定时器重复发送
  - 有文件路径时编辑区 read-only

端口:
  - sendData(QByteArray): 解析后的二进制数据

Hex 解析规则:
  1. 去除所有空白字符（空格、换行、制表符）
  2. 奇数长度末尾补 '0'
  3. 每两个 hex 字符转一个字节
  4. 非法 hex 字符时弹警告，不发送
"""

from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QTextEdit,
                              QPushButton, QCheckBox, QDoubleSpinBox,
                              QLineEdit, QFileDialog, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal, QByteArray, QTimer

from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf, ConnNodeContentWidget


class HexSenderContent(ConnNodeContentWidget):
    """Hex 发送器内容部件 — Hex 编辑 + 文件加载 + 定时器发送"""

    sendData = pyqtSignal(QByteArray)  # 解析后的二进制数据

    def initUI(self):
        layout = QVBoxLayout(self)

        # ── 文件路径行 ───────────────────────────────────────
        file_row = QHBoxLayout()
        self.filePathEdit = QLineEdit(self)
        self.filePathEdit.setPlaceholderText("选择 .bin 文件后自动加载为 Hex")
        self.browseBtn = QPushButton("浏览", self)
        file_row.addWidget(self.filePathEdit)
        file_row.addWidget(self.browseBtn)
        layout.addLayout(file_row)

        # ── Hex 编辑区 ──────────────────────────────────────
        self.hexEdit = QTextEdit(self)
        self.hexEdit.setPlaceholderText(
            "输入 Hex 字节，如:\n"
            "AA 55 01 02 03\n"
            "0A 0B 0C 0D"
        )
        layout.addWidget(self.hexEdit)

        # ── 发送控制 ────────────────────────────────────────
        self.timerDurationSetter = QDoubleSpinBox(self)
        self.timerDurationSetter.setMinimum(0.01)
        self.timerDurationSetter.setDecimals(3)
        self.timerDurationSetter.setValue(1.0)
        layout.addWidget(self.timerDurationSetter)

        self.timerEnable = QCheckBox("启用定时器", self)
        layout.addWidget(self.timerEnable)

        self.sendBtn = QPushButton("发送", self)
        layout.addWidget(self.sendBtn)

        # ── 信号连接 ────────────────────────────────────────
        self.sendBtn.clicked.connect(self._sendHex)
        self.timerEnable.stateChanged.connect(self._onTimerEnableChanged)
        self.timerDurationSetter.valueChanged.connect(self._onTimerDurationChanged)
        self.browseBtn.clicked.connect(self._onBrowseFile)
        self.filePathEdit.textChanged.connect(self._onFilePathChanged)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._sendHex)

        # ── 样式 ────────────────────────────────────────────
        self.setStyleSheet("""
            QCheckBox { color: #e0e0e0; }
            QLineEdit {
                background-color: #202020; color: #e0e0e0;
                border: 1px solid #404040; padding: 2px 4px;
            }
        """)

        self.resize(200, 280)

    # ── Hex 解析 ────────────────────────────────────────────

    @staticmethod
    def _hexToBytes(hex_text: str) -> QByteArray:
        """将 Hex 文本解析为 QByteArray

        规则:
          - 去除所有空白字符
          - 奇数长度末尾补 '0'
          - bytes.fromhex() 转换
        """
        clean = "".join(hex_text.split())
        if not clean:
            return QByteArray()
        if len(clean) % 2:
            clean += "0"
        try:
            raw = bytes.fromhex(clean)
            return QByteArray(raw)
        except ValueError:
            return None

    # ── 文件路径处理 ────────────────────────────────────────

    def _onBrowseFile(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择二进制文件", "",
            "二进制文件 (*.bin *.dat);;所有文件 (*)"
        )
        if file_path:
            self.filePathEdit.setText(file_path)

    def _onFilePathChanged(self, path: str):
        """文件路径变更 — 加载文件内容（不会锁定编辑器）"""
        if path:
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                # 转换为大写 Hex 字符串，空格分隔
                hex_str = " ".join(f"{b:02X}" for b in raw)
                self.hexEdit.setPlainText(hex_str)
            except Exception as e:
                from conn_utils import SimpleLogger
                SimpleLogger.instance().easyWarning(
                    f"Hex发送器: 无法读取文件 {path}: {e}"
                )
                self.filePathEdit.setText("")

    # ── 发送 ────────────────────────────────────────────────

    def _sendHex(self):
        text = self.hexEdit.toPlainText()
        data = self._hexToBytes(text)
        if data is None:
            QMessageBox.warning(self, "Hex 格式错误",
                                "Hex 字符串包含非法字符，请检查输入。\n"
                                "允许的字符: 0-9, A-F, a-f, 空格, 换行")
            return
        if data:
            self.sendData.emit(data)

    # ── 定时器 ──────────────────────────────────────────────

    def _onTimerEnableChanged(self, state: int):
        if state == Qt.Checked:
            interval = int(max(self.timerDurationSetter.value(), 0.01) * 1000)
            self.timer.start(interval)
        else:
            self.timer.stop()

    def _onTimerDurationChanged(self, value: float):
        self.timer.stop()
        if self.timerEnable.isChecked():
            self.timer.start(int(max(value, 0.01) * 1000))

    # ── 生命周期 ────────────────────────────────────────────

    def cleanup(self):
        self.timer.stop()


@register_node()
class HexSenderNode(ConnNode):
    tppath = ("数据源", "Hex发送器")
    icon = "icons/emitter.png"
    name = "Hex发送器"
    tooltip = "编辑 Hex 字节或加载二进制文件，支持定时器发送"
    conn_title = "Hex发送器"

    NodeContent_class = HexSenderContent

    def __init__(self, scene):
        super().__init__(scene,
            signalsConf=[
                ConnSocketConf(
                    socketType=2,
                    key="sendData",
                    tooltip="发送 Hex 解析后的 QByteArray 二进制数据",
                    name="数据",
                    argsType=(QByteArray,)
                ),
            ]
        )
        self.registerSignal("sendData", self.content.sendData)

    def serialize(self):
        res = super().serialize()
        res['hex_content'] = self.content.hexEdit.toPlainText()
        res['file_path'] = self.content.filePathEdit.text()
        res['timer_enabled'] = self.content.timerEnable.isChecked()
        res['timer_duration'] = self.content.timerDurationSetter.value()
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        self.content.filePathEdit.setText(data.get('file_path', ""))
        self.content.timerDurationSetter.setValue(data.get('timer_duration', 1.0))
        self.content.timerEnable.setChecked(data.get('timer_enabled', False))
        # hex_content 在 file_path 有效时会被文件内容覆盖
        self.content.hexEdit.setPlainText(data.get('hex_content', ""))
        return res
