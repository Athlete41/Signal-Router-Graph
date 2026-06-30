"""
协议解析器 V3 — 协议解析节点

变体列表:
  - 协议解析器V3-1ch: 1 个输出端口，仅接受 channel_id=0
  - 协议解析器V3-2ch: 2 个输出端口，接受 channel_id=0~1（支持偏移）
  - 协议解析器V3-4ch: 4 个输出端口，接受 channel_id=0~3（支持偏移）

设计文档: connnodes/protocol_parser_v3/协议解析器V3设计文档.md
协议文档: connnodes/waveform_protocol_v3.md
"""

from __future__ import annotations

from typing import ClassVar

from PyQt5.QtCore import QByteArray

from conn_base import ConnNode, ConnSocketConf
from conn_conf import register_node, set_node_display
from nodeeditor.node_socket import LEFT_CENTER, RIGHT_CENTER

from .parser_widget import ProtocolParserContent


# ═══════════════════════════════════════════════════════════════
# 基类 — 共享逻辑
# ═══════════════════════════════════════════════════════════════

class _ProtocolParserV3Base(ConnNode):
    """协议解析器 V3 基类

    子类必须覆盖 CHANNEL_COUNT：
        CHANNEL_COUNT = 1 | 2 | 4

    端口约定:
        输入: 1 个 QByteArray，key="dataInput"
        输出: N 个 (object, int)，key="ch0"~"ch{N-1}"
        详见设计文档「端口约定」

    约束:
        1. 输出端口数由 CHANNEL_COUNT 在声明时固定，不支持运行时增减
        2. 通道偏移 (channel_offset) 影响路由逻辑（见设计文档「路由逻辑」）
        3. 协议解析在独立 QThread 中执行（_ProtocolParserWorker）
        4. 端口声明顺序对反序列化敏感，必须追加在列表末尾
    """

    # ── 子类必须覆写 ─────────────────────────────────
    CHANNEL_COUNT: ClassVar[int]       # 1 / 2 / 4
    tppath: ClassVar[tuple[str, str]]
    icon: ClassVar[str]
    name: ClassVar[str]
    tooltip: ClassVar[str]
    conn_title: ClassVar[str]

    NodeContent_class = ProtocolParserContent

    def initInnerClasses(self):
        """创建内容部件（使用 CHANNEL_COUNT）

        框架默认的 initInnerClasses 只传 node 一个参数，
        ProtocolParserContent 还需要 ch_count，故在此覆写。
        """
        node_content_class = self.getNodeContentClass()
        if node_content_class is not None:
            self.content = node_content_class(self, self.CHANNEL_COUNT)
        graphics_node_class = self.getGraphicsNodeClass()
        if graphics_node_class is not None:
            self.grNode = graphics_node_class(self)

    def __init__(self, scene):
        """初始化节点、端口、内容部件

        约束:
            1. slotsConf: 一个输入端口
               key="dataInput", argsType=(QByteArray,)
            2. signalsConf: 按 CHANNEL_COUNT 生成 N 个输出端口
               key="ch0", "ch1", ..., "ch{N-1}"
               每个端口 argsType=(object, int)
            3. registerSlot("dataInput", self.content._worker.writeData)
            4. registerSignal("ch{i}", self.content.ch{i})  对每个通道
            5. ★ 内容部件在 initInnerClasses 中创建（不是这里）
            6. 详见设计文档「端口约定」「内容部件信号创建」
        """
        # 构建输出端口配置
        signalsConf = [
            ConnSocketConf(
                socketType=2,
                key=f"ch{i}",
                name=f"输出{i+1}",
                tooltip=f"输出端口 {i+1} (ndarray, interval_us)",
                argsType=(object, int)
            )
            for i in range(self.CHANNEL_COUNT)
        ]

        super().__init__(scene,
            signalsConf=signalsConf,
            slotsConf=[
                ConnSocketConf(
                    socketType=1,
                    key="dataInput",
                    name="输入",
                    tooltip="接收 V3 协议 QByteArray 数据",
                    argsType=(QByteArray,)
                ),
            ]
        )

        # 注册信号/槽
        self.registerSlot("dataInput", self.content._worker.writeData)
        for i in range(self.CHANNEL_COUNT):
            self.registerSignal(f"ch{i}",
                                getattr(self.content, f"ch{i}"))

    def initSettings(self) -> None:
        """初始化节点设置"""
        super().initSettings()
        self.input_socket_position = LEFT_CENTER
        self.output_socket_position = RIGHT_CENTER

    def serialize(self) -> dict:
        """序列化节点状态

        返回格式:
            {"channel_offset": int}   # 默认 0，范围 0~255

        约束:
            从 self.content._channel_offset 取值
        """
        res = super().serialize()
        res["channel_offset"] = self.content._channel_offset
        return res

    def deserialize(self, data: dict, hashmap: dict | None = None,
                    restore_id: bool = True):
        """反序列化恢复节点状态

        约束:
            1. 先调用 super().deserialize()
            2. 恢复 channel_offset: data.get("channel_offset", 0)
            3. ★ 端口数量由 CHANNEL_COUNT 决定（不从 JSON 读取）
            4. 旧版 JSON 可能不含 "channel_offset" 字段（向后兼容）
        """
        res = super().deserialize(data, hashmap, restore_id)
        self.content._channel_offset = data.get("channel_offset", 0)
        self.content.offset_spin.setValue(self.content._channel_offset)
        return res


# ── 分类显示元数据 ──────────────────────────────────────────
set_node_display(
    tppath=("数据处理",),
    name="数据处理",
    tooltip="数据分析与协议解析节点",
)


# ═══════════════════════════════════════════════════════════════
# 变体注册
# ═══════════════════════════════════════════════════════════════

@register_node()
class ProtocolParserV3_1ch(_ProtocolParserV3Base):
    """协议解析器 V3 — 单通道（仅接受 channel_id=0）"""
    CHANNEL_COUNT = 1
    tppath = ("数据处理", "协议解析器V3-1ch")
    icon = "icons/parser.png"
    name = "协议解析器V3-1ch"
    tooltip = "V3 协议解析，单通道输出，仅接受 channel_id=0（可偏移）"
    conn_title = "协议解析器V3-1ch"


@register_node()
class ProtocolParserV3_2ch(_ProtocolParserV3Base):
    """协议解析器 V3 — 双通道（channel_id=0~1，偏移映射）"""
    CHANNEL_COUNT = 2
    tppath = ("数据处理", "协议解析器V3-2ch")
    icon = "icons/parser.png"
    name = "协议解析器V3-2ch"
    tooltip = "V3 协议解析，双通道输出，接受 channel_id=0~1（可偏移）"
    conn_title = "协议解析器V3-2ch"


@register_node()
class ProtocolParserV3_4ch(_ProtocolParserV3Base):
    """协议解析器 V3 — 四通道（channel_id=0~3，偏移映射）"""
    CHANNEL_COUNT = 4
    tppath = ("数据处理", "协议解析器V3-4ch")
    icon = "icons/parser.png"
    name = "协议解析器V3-4ch"
    tooltip = "V3 协议解析，四通道输出，接受 channel_id=0~3（可偏移）"
    conn_title = "协议解析器V3-4ch"
