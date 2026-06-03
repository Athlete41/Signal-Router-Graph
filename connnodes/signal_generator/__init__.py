from .signal_generator_widget import SignalGeneratorContent
from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf
from PyQt5.QtCore import QByteArray
from nodeeditor.node_socket import RIGHT_CENTER


@register_node()
class SignalGeneratorNode(ConnNode):
    tppath = ("数据源", "信号发生器")
    icon = "icons/emitter.png"
    name = "信号发生器"
    tooltip = "生成正弦波/方波/三角波/锯齿波信号，按协议编码为 QByteArray 输出，可调频率/幅值/采样率"
    conn_title = "信号发生器"

    NodeContent_class = SignalGeneratorContent

    def __init__(self, scene):
        super().__init__(scene,
            signalsConf=[
                ConnSocketConf(
                    socketType=2,
                    key="dataOutput",
                    tooltip="按协议编码的正弦波数据 (QByteArray)，包含帧头+采样间隔+float数组+校验",
                    name="协议数据",
                    argsType=(QByteArray,)
                ),
            ]
        )
        self.registerSignal("dataOutput", self.content.dataOutput)

    def initSettings(self):
        super().initSettings()
        self.output_socket_position = RIGHT_CENTER

    def serialize(self):
        res = super().serialize()
        res["freq"] = self.content._freqSpin.value()
        res["amp"] = self.content._ampSpin.value()
        res["sample_rate"] = self.content._sampleRateSpin.value()
        res["packet_size"] = self.content._packetSizeSpin.value()
        res["waveform_type"] = self.content._typeCombo.currentIndex()
        res["started"] = self.content._startBtn.isChecked()
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        self.content._freqSpin.setValue(data.get("freq", 1.0))
        self.content._ampSpin.setValue(data.get("amp", 1.0))
        self.content._sampleRateSpin.setValue(data.get("sample_rate", 1000))
        self.content._packetSizeSpin.setValue(data.get("packet_size", 100))
        self.content._typeCombo.setCurrentIndex(data.get("waveform_type", 0))
        started = data.get("started", False)
        self.content._startBtn.setChecked(started)
        if started:
            self.content._phase = 0.0
            self.content._timer.start(self.content._calcInterval())
            self.content._startBtn.setText("停止")
        return res
