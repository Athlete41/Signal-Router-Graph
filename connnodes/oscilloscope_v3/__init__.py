"""
示波器 V3 — 示波器节点

固定 4 输入通道（ch0~ch3），接收协议解析器输出的 (ndarray, gap_count, interval_us)。

设计文档: connnodes/oscilloscope_v3/（6 份 .md，实现在 .py 中后已删除）
"""

from __future__ import annotations

from conn_base import ConnNode, ConnSocketConf
from conn_conf import register_node, set_node_display
from nodeeditor.node_socket import LEFT_CENTER, RIGHT_CENTER

from .oscilloscope_content import OscilloscopeContent


# ── 分类显示元数据 ──────────────────────────────────────────
set_node_display(
    tppath=("显示",),
    name="显示",
    tooltip="波形显示与可视化节点",
)


@register_node()
class OscilloscopeNodeV3(ConnNode):
    """示波器 V3 — 4 通道波形显示

    端口约定:
        输入: 4 个 (object, int, int)，key="ch0"~"ch3"
        输出: 无

    数据流:
        协议解析器 → ConnEdge(ch{i}) → worker.writeData()
            → NumpyRingBuffer → 包络计算 → 画板读取

    线程模型:
        4 个独立 QThread（每通道一个 OscilloscopeSampler）
        + 主线程 WaveformWidget（QTimer 主动绘制）
    """

    tppath = ("显示", "示波器 V3")
    icon = "icons/oscilloscope.png"
    name = "示波器V3"
    tooltip = "V3 示波器 — 4 通道波形显示（接收解析器数据）"
    conn_title = "示波器 V3"

    NodeContent_class = OscilloscopeContent

    def __init__(self, scene):
        """初始化节点 — 4 个输入端口，无输出端口"""
        super().__init__(scene,
            signalsConf=[],   # 无输出
            slotsConf=[
                ConnSocketConf(
                    socketType=1,
                    key="ch0",
                    name="CH0",
                    tooltip="通道 0 输入 (ndarray, gap_count, interval_us)",
                    argsType=(object, int, int)
                ),
                ConnSocketConf(
                    socketType=1,
                    key="ch1",
                    name="CH1",
                    tooltip="通道 1 输入 (ndarray, gap_count, interval_us)",
                    argsType=(object, int, int)
                ),
                ConnSocketConf(
                    socketType=1,
                    key="ch2",
                    name="CH2",
                    tooltip="通道 2 输入 (ndarray, gap_count, interval_us)",
                    argsType=(object, int, int)
                ),
                ConnSocketConf(
                    socketType=1,
                    key="ch3",
                    name="CH3",
                    tooltip="通道 3 输入 (ndarray, gap_count, interval_us)",
                    argsType=(object, int, int)
                ),
            ]
        )

        # 注册输入槽 — 每个通道对应一个 Worker.writeData
        for i in range(4):
            self.registerSlot(f"ch{i}",
                              self.content._workers[i].writeData)

    def initSettings(self) -> None:
        """初始化节点设置"""
        super().initSettings()
        self.input_socket_position = LEFT_CENTER
        # 无输出端口，不需设置 output_socket_position

    def serialize(self) -> dict:
        """序列化节点状态"""
        res = super().serialize()
        state = self.content.get_state()
        res.update(state)
        return res

    def deserialize(self, data: dict, hashmap: dict | None = None,
                    restore_id: bool = True):
        """反序列化恢复节点状态"""
        res = super().deserialize(data, hashmap, restore_id)
        self.content.set_state(data)
        return res
