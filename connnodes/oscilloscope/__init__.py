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
    icon = "icons/oscilloscope.png"
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
                ConnSocketConf(
                    socketType=1,
                    key="writeJsonData",
                    tooltip="接收 dict 格式波形数据: {点, 采样间隔_us, gap数}",
                    name="JSON 数据",
                    argsType=(dict,)
                ),
            ]
        )
        # 注册工作线程对象的槽函数（跨线程由 AutoConnection 自动处理）
        self.registerSlot("writeData", self.content.sampler.writeData)
        self.registerSlot("writeJsonData", self.content.sampler.writeJsonData)

    def initSettings(self):
        super().initSettings()
        self.input_socket_position = LEFT_CENTER

    def serialize(self):
        res = super().serialize()
        res["fps"] = self.content._fpsSpin.value()
        res["buffer_size"] = self.content._bufferSpin.value()
        res["temp_buffer_size"] = self.content._tempBufferSpin.value()
        res["sample_freq_hz"] = self.content._sampleFreqSpin.value()
        res["time_window"] = self.content._timeWindowSpin.value()
        res["view_offset"] = self.content._view_offset
        res["y_range"] = self.content._y_range
        res["y_offset"] = self.content._y_offset
        res["wave_line_width"] = self.content._lineWidthSpin.value()
        res["wave_color"] = self.content._waveform._wave_color.name()
        res["started"] = self.content._startBtn.isChecked()
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        self.content._fpsSpin.setValue(data.get("fps", 30))
        self.content._bufferSpin.setValue(data.get("buffer_size", 1000))
        self.content._tempBufferSpin.setValue(data.get("temp_buffer_size", 5000))
        # 采样频率：向后兼容旧 key (sample_freq_khz 单位为 kHz)
        if "sample_freq_hz" in data:
            self.content._sampleFreqSpin.setValue(data["sample_freq_hz"])
        elif "sample_freq_khz" in data:
            self.content._sampleFreqSpin.setValue(data["sample_freq_khz"] * 1000.0)
        else:
            self.content._sampleFreqSpin.setValue(1000.0)
        self.content._timeWindowSpin.setValue(data.get("time_window", 1.0))
        self.content._view_offset = data.get("view_offset", 0)

        # Y 轴：向后兼容旧文件（view_y_min/max）
        if "y_range" in data and "y_offset" in data:
            self.content._y_range = data["y_range"]
            self.content._y_offset = data["y_offset"]
        else:
            vy_min = data.get("view_y_min", -5.0)
            vy_max = data.get("view_y_max", 5.0)
            self.content._setYFromMinMax(vy_min, vy_max)
        self.content._yRangeSpin.setValue(self.content._y_range)
        self.content._yOffsetSpin.setValue(self.content._y_offset)

        # 波形样式
        self.content._lineWidthSpin.setValue(data.get("wave_line_width", 2))
        wave_color_hex = data.get("wave_color", "#00dc00")
        self.content.setWaveColorFromHex(wave_color_hex)

        started = data.get("started", False)
        self.content._startBtn.setChecked(started)
        if started:
            self.content._startRequested.emit()
            self.content._startBtn.setText("Stop")
        return res
