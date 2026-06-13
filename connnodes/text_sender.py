"""
文本发送器 — 文本编辑 + 文件加载 + 定时器发送

继承自原 data_sender.py，新增文件路径输入功能：
- 有文件路径时，textEdit 显示文件内容并设为 read-only
- 无文件路径时，正常编辑文本
- 定时器每次 tick 发送整个编辑器内容

端口:
  - sendDataNotify(QByteArray): 文本编码后的二进制数据
  - sendTextNotify(str): 纯文本字符串
"""

from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QTextEdit,
                              QPushButton, QCheckBox, QDoubleSpinBox,
                              QLineEdit, QFileDialog)
from PyQt5.QtCore import Qt, pyqtSignal, QByteArray, QTimer

from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf, ConnNodeContentWidget


class TextSenderContent(ConnNodeContentWidget):
    """文本发送器内容部件 — 文本编辑 + 文件加载 + 定时器发送"""

    sendDataNotify = pyqtSignal(QByteArray)   # 文本编码后的二进制数据
    sendTextNotify = pyqtSignal(str)           # 纯文本字符串

    def initUI(self):
        layout = QVBoxLayout(self)

        # ── 文件路径行（新增） ───────────────────────────────
        file_row = QHBoxLayout()
        self.filePathEdit = QLineEdit(self)
        self.filePathEdit.setPlaceholderText("选择文件后自动加载，清空后恢复编辑")
        self.browseBtn = QPushButton("浏览", self)
        file_row.addWidget(self.filePathEdit)
        file_row.addWidget(self.browseBtn)
        layout.addLayout(file_row)

        # ── 文本编辑区 ──────────────────────────────────────
        self.textEdit = QTextEdit(self)
        layout.addWidget(self.textEdit)

        # ── 发送控制 ────────────────────────────────────────
        self.autoLineBreak = QCheckBox("自动新行", self)
        self.autoLineBreak.setChecked(True)
        layout.addWidget(self.autoLineBreak)

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
        self.sendBtn.clicked.connect(self.sendData)
        self.timerEnable.stateChanged.connect(self._onTimerEnableChanged)
        self.timerDurationSetter.valueChanged.connect(self._onTimerDurationChanged)
        self.browseBtn.clicked.connect(self._onBrowseFile)
        self.filePathEdit.textChanged.connect(self._onFilePathChanged)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sendData)

        # ── 样式 ────────────────────────────────────────────
        self.setStyleSheet("""
            QCheckBox { color: #e0e0e0; }
            QLineEdit {
                background-color: #202020; color: #e0e0e0;
                border: 1px solid #404040; padding: 2px 4px;
            }
        """)

        self.resize(200, 280)

    # ── 文件路径处理 ────────────────────────────────────────

    def _onBrowseFile(self):
        """打开文件选择对话框"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择文本文件", "",
            "文本文件 (*.txt *.csv *.log *.json *.xml *.md);;所有文件 (*)"
        )
        if file_path:
            self.filePathEdit.setText(file_path)

    def _onFilePathChanged(self, path: str):
        """文件路径变更 — 加载文件内容（不会锁定编辑器）"""
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.textEdit.setPlainText(content)
            except Exception as e:
                from conn_utils import SimpleLogger
                SimpleLogger.instance().easyWarning(
                    f"文本发送器: 无法读取文件 {path}: {e}"
                )
                self.filePathEdit.setText("")

    # ── 发送 ────────────────────────────────────────────────

    def sendData(self):
        text = self.textEdit.toPlainText()
        if self.autoLineBreak.isChecked():
            text += "\n"
        if text:
            self.sendDataNotify.emit(QByteArray(text.encode("utf-8")))
            self.sendTextNotify.emit(text)

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
class TextSenderNode(ConnNode):
    tppath = ("数据源", "文本发送器")
    icon = "icons/emitter.png"
    name = "文本发送器"
    tooltip = "编辑文本或加载文本文件，支持定时器发送"
    conn_title = "文本发送器"

    NodeContent_class = TextSenderContent

    def __init__(self, scene):
        super().__init__(scene,
            signalsConf=[
                ConnSocketConf(
                    socketType=2,
                    key="sendDataNotify",
                    tooltip="会将字符串转换为 QByteArray 类型后发送",
                    name="数据",
                    argsType=(QByteArray,)
                ),
                ConnSocketConf(
                    socketType=2,
                    key="sendTextNotify",
                    tooltip="直接发送文本字符串",
                    name="文本",
                    argsType=(str,)
                ),
            ]
        )
        self.registerSignal("sendDataNotify", self.content.sendDataNotify)
        self.registerSignal("sendTextNotify", self.content.sendTextNotify)

    def serialize(self):
        res = super().serialize()
        res['text_content'] = self.content.textEdit.toPlainText()
        res['auto_line_break_enabled'] = self.content.autoLineBreak.isChecked()
        res['timer_enabled'] = self.content.timerEnable.isChecked()
        res['timer_duration'] = self.content.timerDurationSetter.value()
        res['file_path'] = self.content.filePathEdit.text()
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        self.content.filePathEdit.setText(data.get('file_path', ""))
        self.content.autoLineBreak.setChecked(data.get('auto_line_break_enabled', True))
        self.content.timerDurationSetter.setValue(data.get('timer_duration', 1.0))
        self.content.timerEnable.setChecked(data.get('timer_enabled', False))
        # text_content 在 file_path 有效时会被文件内容覆盖
        self.content.textEdit.setPlainText(data.get('text_content', ""))
        return res
