"""
示波器 V3 — 示波器显示节点

双通道接收型节点，从协议解析器 V3 接收 (ndarray, interval_us) 数据。
显示波形，不包含触发逻辑（触发由独立的 trigger_v3 节点处理）。

"""

from __future__ import annotations

from conn_base import ConnNode, ConnSocketConf
from conn_conf import register_node
from nodeeditor.node_socket import LEFT_CENTER, RIGHT_CENTER

from .oscilloscope_widget import OscilloscopeV3Content


@register_node()
class OscilloscopeV3Node(ConnNode):
    """示波器 V3 节点

    双通道输入，接收协议解析器 V3 的 (ndarray, interval_us)。
    显示波形，不包含触发逻辑（触发由独立的 trigger_v3 节点处理）。

    端口约定:
        输入 1: (object, int) — 数据
        输入 2: (object, int) — 数据

    约束:
        1. 内容部件 OscilloscopeV3Content 管理两个工作线程
        2. 反序列化依赖端口声明顺序，新增端口必须追加在末尾
    """

    tppath = ("可视化", "示波器V3")
    icon = "icons/oscilloscope.png"
    name = "示波器V3"
    tooltip = ("双通道示波器\n"
               "滚轮: 缩放时间轴 | Shift+滚轮: 缩放幅值\n"
               "拖拽: 水平滚动 | Shift+拖拽: 调偏移\n"
               "双击: 回自动滚动")
    conn_title = "示波器V3"
    NodeContent_class = OscilloscopeV3Content

    def __init__(self, scene):
        super().__init__(scene,
            signalsConf=[],
            slotsConf=[
                ConnSocketConf(
                    socketType=1,
                    key="input_1",
                    name="输入1",
                    tooltip="数据输入 1 (ndarray, interval_us)",
                    argsType=(object, int)
                ),
                ConnSocketConf(
                    socketType=1,
                    key="input_2",
                    name="输入2",
                    tooltip="数据输入 2 (ndarray, interval_us)",
                    argsType=(object, int)
                ),
            ]
        )

        self.registerSlot("input_1", self.content._dc.on_data_1)
        self.registerSlot("input_2", self.content._dc.on_data_2)

    def initSettings(self) -> None:
        super().initSettings()
        self.input_socket_position = LEFT_CENTER
        self.output_socket_position = RIGHT_CENTER

    def serialize(self) -> dict:
        res = super().serialize()
        c = self.content
        wv = c.ui.waveform_view
        res.update({
            "x_window_ms": wv.get_x_window_ms(),
            "y_window_mv_1": wv.get_y_window_mv_1(),
            "y_offset_mv_1": wv.get_y_offset_mv_1(),
            "y_window_mv_2": wv.get_y_window_mv_2(),
            "y_offset_mv_2": wv.get_y_offset_mv_2(),
            "x_div": c.ui.x_div_spin.value(),
            "y_div": c.ui.y_div_spin.value(),
            "fps": c.ui.fps_spin.value(),
            "mem_depth": c.ui.memory_depth_spin.value(),
            "show_scale": c.ui.show_scale_check.isChecked(),
        })
        return res

    def deserialize(self, data: dict, hashmap: dict | None = None,
                    restore_id: bool = True):
        res = super().deserialize(data, hashmap, restore_id)
        c = self.content
        ui = c.ui
        c.blockSignals(True)
        try:
            # 新字段名 → UI 控件名映射
            field_map = [
                ("x_window_ms", ui.x_window_ms_spin, int),
                ("y_window_mv_1", ui.y_window_mv_1_spin, float),
                ("y_offset_mv_1", ui.y_offset_mv_1_spin, float),
                ("y_window_mv_2", ui.y_window_mv_2_spin, float),
                ("y_offset_mv_2", ui.y_offset_mv_2_spin, float),
                ("x_div", ui.x_div_spin, float),
                ("y_div", ui.y_div_spin, float),
                ("fps", ui.fps_spin, int),
                ("mem_depth", ui.memory_depth_spin, int),
            ]

            for key, widget, _ in field_map:
                if key in data:
                    widget.setValue(data[key])
                else:
                    # 向后兼容：旧字段名 → 新字段名
                    old_map = {
                        "voltage_range_1": "y_window_mv_1",
                        "voff_1": "y_offset_mv_1",
                        "voltage_range_2": "y_window_mv_2",
                        "voff_2": "y_offset_mv_2",
                    }
                    # 旧文件的数据键名直接映射
                    for old_key, new_key in old_map.items():
                        if old_key in data and new_key == key:
                            widget.setValue(float(data[old_key]))
                            break
                    else:
                        # 再试 V2 格式：timebase*h_div, vdiv*v_div
                        if key == "x_window_ms" and "timebase" in data and "h_div" in data:
                            ui.x_window_ms_spin.setValue(data["timebase"] * data["h_div"] / 1000)
                        elif key == "y_window_mv_1" and "vdiv_1" in data and "v_div" in data:
                            ui.y_window_mv_1_spin.setValue(data["vdiv_1"] * data["v_div"])
                        elif key == "y_window_mv_2" and "vdiv_2" in data and "v_div" in data:
                            ui.y_window_mv_2_spin.setValue(data["vdiv_2"] * data["v_div"])

            # V2 的 time_window_us → V3 的 x_window_ms
            if "x_window_ms" not in data and "time_window_us" in data:
                ui.x_window_ms_spin.setValue(data["time_window_us"] // 1000)

            # 刻度绘制状态（默认 True，旧文件没有此字段时保持默认）
            if "show_scale" in data:
                ui.show_scale_check.setChecked(data["show_scale"])

        finally:
            c.blockSignals(False)
        return res
