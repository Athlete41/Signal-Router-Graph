from qtpy.QtWidgets import QTextEdit, QVBoxLayout, QPushButton, QCheckBox, QDoubleSpinBox
from qtpy.QtCore import Qt

from PyQt5.QtCore import pyqtSignal, QByteArray, QTimer

from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf
from conn_base import ConnNodeContentWidget



class DataSenderAdvancedContent(ConnNodeContentWidget):
    sendDataNotify = pyqtSignal(QByteArray)
    sendTextNotify = pyqtSignal(str)

    def initUI(self):
        layout = QVBoxLayout(self)
        self.textEdit = QTextEdit(self)
        self.autoLineBreak = QCheckBox(self)
        self.sendBtn = QPushButton("发送", self)
        self.timer = QTimer(self)
        self.timerEnable = QCheckBox(self)
        self.timerDurationSetter = QDoubleSpinBox(self)


        self.setLayout(layout)
        layout.addWidget(self.textEdit)
        layout.addWidget(self.autoLineBreak)
        layout.addWidget(self.timerDurationSetter)
        layout.addWidget(self.timerEnable)
        layout.addWidget(self.sendBtn)
        
        self.timerEnable.setText("启用定时器")
        self.autoLineBreak.setText("自动新行")
        self.autoLineBreak.setChecked(True)
        self.sendBtn.clicked.connect(self.sendData)
        self.timerEnable.stateChanged.connect(self.timerEnableChangedHandler)
        self.timer.timeout.connect(self.sendData)
        self.timerDurationSetter.valueChanged.connect(self.timerDurationChangedHandler)
        self.timerDurationSetter.setMinimum(0.01)
        self.timerDurationSetter.setDecimals(3)
        self.timerDurationSetter.setValue(1)

        self.resize(200, 200)


        # TODO 暂时没找到细致修改全局样式的方法, 这里先简单处理
        self.setStyleSheet("""                 
QCheckBox {
    color: #e0e0e0;
}
""")

    def timerEnableChangedHandler(self, state: int):
        if state == Qt.Checked:
            self.timer.start(int(max(self.timerDurationSetter.value(), 0.01) * 1000))
        else:
            self.timer.stop()

    def timerDurationChangedHandler(self, value: float):
        self.timer.stop()
        if self.timerEnable.isChecked(): self.timer.start(int(max(value, 0.01) * 1000))

    def sendData(self):
        text = self.textEdit.toPlainText() + ("\n" if self.autoLineBreak.isChecked() else "")
        if text != "":
            self.sendDataNotify.emit(QByteArray(text.encode("utf-8")))
            self.sendTextNotify.emit(text)


    def cleanup(self):
        ...

@register_node()
class DataSenderAdvancedNode(ConnNode):
    tppath = ("数据源", "发送器")
    icon = "icons/emitter.png"
    name = "发送器"
    tooltip = "可以发送 QByteArray 类型数据, 支持定时器发送"
    conn_title = "发送器"

    NodeContent_class = DataSenderAdvancedContent

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
                )
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
        
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)

        self.content.textEdit.setPlainText(data.get('text_content', ""))
        self.content.autoLineBreak.setChecked(data.get('auto_line_break_enabled', True))
        self.content.timerEnable.setChecked(data.get('timer_enabled', False))
        self.content.timerDurationSetter.setValue(data.get('timer_duration', 1.0))

        return res
    