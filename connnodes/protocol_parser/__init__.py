"""
协议解析器节点 — 将 QByteArray 协议包解码为 dict 格式

多线程：解码在工作线程执行，不阻塞主线程 UI。
用于将二进制协议数据转换为结构化 dict，方便与支持 dict 端口的节点配合。
"""
from PyQt5.QtWidgets import QLabel, QVBoxLayout
from PyQt5.QtCore import pyqtSignal, pyqtSlot, QObject, QThread, Qt, QByteArray
from conn_base import ConnNode, ConnNodeContentWidget, ConnSocketConf
from conn_conf import register_node
from conn_utils import ThreadManager
from connnodes.waveform_protocol import decode_packet
from nodeeditor.node_socket import LEFT_CENTER, RIGHT_CENTER


# ═══════════════════════════════════════════════════════════════════════
# 工作线程核心
# ═══════════════════════════════════════════════════════════════════════

class _ParserWorker(QObject):
    """协议解析工作线程 — QByteArray → dict，解码不阻塞主线程"""

    resultReady = pyqtSignal(dict)
    decodeFailed = pyqtSignal()

    @pyqtSlot(QByteArray)
    def processData(self, qba: QByteArray):
        """接收协议包 → 解码 → 发射结果（在工作线程执行）"""
        result = decode_packet(qba)
        if result is None:
            self.decodeFailed.emit()
            return

        d = {
            "点": result["data"],
            "采样间隔_us": result["sampling_interval_us"],
            "gap数": result["gap_count"],
        }
        self.resultReady.emit(d)


# ═══════════════════════════════════════════════════════════════════════
# 内容部件（主线程）
# ═══════════════════════════════════════════════════════════════════════

class ProtocolParserContent(ConnNodeContentWidget):
    """协议解析器内容部件 — 管理工作线程生命周期"""

    jsonOutput = pyqtSignal(dict)

    def initUI(self):
        # ── 工作线程初始化 ──
        self._worker = _ParserWorker()
        self._thread = QThread()
        self._thread.start()
        ThreadManager.instance().register_thread(self._thread)
        self._worker.moveToThread(self._thread)
        self._worker.resultReady.connect(self._onResultReady)
        self._worker.decodeFailed.connect(self._onDecodeFailed)

        # ── UI ──
        self._statusLabel = QLabel("等待数据...")
        self._statusLabel.setAlignment(Qt.AlignCenter)
        self._statusLabel.setStyleSheet(
            "color: #888; border: none; font-size: 11px;"
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self._statusLabel)
        self.resize(160, 60)

    # ── 槽（主线程） ──

    @pyqtSlot(dict)
    def _onResultReady(self, d: dict):
        """工作线程解码成功 → 更新状态 + 转发到输出端口"""
        n = len(d.get("点", []))
        self._statusLabel.setText(f"✅ {n} 点 | {d['采样间隔_us']}μs/点")
        self.jsonOutput.emit(d)

    @pyqtSlot()
    def _onDecodeFailed(self):
        """工作线程解码失败 → 更新状态"""
        self._statusLabel.setText("❌ 解码失败")

    def cleanup(self):
        """清理工作线程"""
        self._worker.deleteLater()
        self._thread.quit()
        self._thread.wait(3000)
        self._thread.deleteLater()


@register_node()
class ProtocolParserNode(ConnNode):
    tppath = ("数据工具", "协议解析器")
    icon = ""
    name = "协议解析器"
    tooltip = "将 QByteArray 协议包解析为 dict 格式（JSON），用于与其他 dict 端口的节点直连"
    conn_title = "协议解析器"

    NodeContent_class = ProtocolParserContent

    def __init__(self, scene):
        super().__init__(scene,
            slotsConf=[
                ConnSocketConf(
                    socketType=1,
                    key="dataInput",
                    tooltip="接收 QByteArray 协议包（waveform_protocol 格式）",
                    name="协议数据",
                    argsType=(QByteArray,)
                ),
            ],
            signalsConf=[
                ConnSocketConf(
                    socketType=2,
                    key="jsonOutput",
                    tooltip="解析后的 dict 格式数据：{点, 采样间隔_us, gap数}",
                    name="JSON 数据",
                    argsType=(dict,)
                ),
            ]
        )
        self.registerSlot("dataInput", self.content._worker.processData)
        self.registerSignal("jsonOutput", self.content.jsonOutput)

    def initSettings(self):
        super().initSettings()
        self.input_socket_position = LEFT_CENTER
        self.output_socket_position = RIGHT_CENTER

    def serialize(self):
        return super().serialize()

    def deserialize(self, data, hashmap={}, restore_id=True):
        return super().deserialize(data, hashmap, restore_id)
