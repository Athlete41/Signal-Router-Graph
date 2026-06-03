from .oscilloscope_widget import OscilloscopeContent
from conn_conf import register_node, set_node_display
from conn_base import ConnNode, ConnSocketConf
from nodeeditor.node_socket import LEFT_CENTER
from PyQt5.QtCore import QByteArray


# 注册 "可视化" 分类的显示元数据
set_node_display(
    tppath=("可视化",),
    tooltip="可视化节点（示波器等）",
    icon="icons/sub.png",
)


@register_node()
class OscilloscopeNode(ConnNode):
    tppath = ("可视化", "示波器")
    icon = "icons/receiver.png"
    name = "示波器"
    tooltip = (
        "示波器节点，接收 QByteArray 协议包，"
        "协议格式: [帧头2B][采样间隔4B][数据数2B][float32数组][校验1B]；"
        "支持放大倍数/偏移调节，多线程环形缓冲区 + 帧同步"
    )
    conn_title = "示波器"

    NodeContent_class = OscilloscopeContent

    def __init__(self, scene):
        super().__init__(scene,
            slotsConf=[
                ConnSocketConf(
                    socketType=1,
                    key="writeData",
                    tooltip=(
                        "接收 QByteArray 协议包，"
                        "协议: 0xAA55 + 采样间隔(uint32) + 数据数(uint16) + float32数组 + XOR校验"
                    ),
                    name="协议数据",
                    argsType=(QByteArray,)
                ),
            ]
        )
        # 注册工作线程对象的槽函数（跨线程由 AutoConnection 自动处理）
        self.registerSlot("writeData", self.content.sampler.writeData)

    def initSettings(self):
        super().initSettings()
        self.input_socket_position = LEFT_CENTER

    def serialize(self):
        res = super().serialize()
        res["fps"] = self.content._fpsSpin.value()
        res["buffer_size"] = self.content._bufferSpin.value()
        res["time_window"] = self.content._timeWindowSpin.value()
        res["amplification"] = self.content._ampSpin.value()
        res["offset"] = self.content._offsetSpin.value()
        res["started"] = self.content._startBtn.isChecked()
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        self.content._fpsSpin.setValue(data.get("fps", 30))
        self.content._bufferSpin.setValue(data.get("buffer_size", 1000))
        self.content._timeWindowSpin.setValue(data.get("time_window", 1.0))
        self.content._ampSpin.setValue(data.get("amplification", 1.0))
        self.content._offsetSpin.setValue(data.get("offset", 0.0))
        started = data.get("started", False)
        self.content._startBtn.setChecked(started)
        if started:
            self.content._startRequested.emit()
            self.content._startBtn.setText("Stop")
        return res
