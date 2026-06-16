"""
协议解析器 V3 — 内容部件 + _ProtocolParserWorker

架构:
    ProtocolParserContent (主线程, ch_count 固定)
      ├── _ProtocolParserWorker (独立 QThread)
      │     ├── _buffer: bytearray          # 累积缓冲区
      │     ├── _pos: int                   # read index 指针
      │     ├── _processBuffer() — 片段重组 + CRC 校验 + 解码
      │     └── op_signal(channel_id, ndarray, gap_count, interval_us)
      │
      ├── ch0 ~ ch{N-1} (pyqtSignal(object, int, int))
      │
      └── UI: 通道偏移 spin、分级日志 checkboxes（错误/警告/信息/调试）

性能优化:
    1. bytes.find() — C 级帧头搜索，比 Python 循环快 10-50×
    2. decode_raw() — 内部快速路径，跳过重复校验
    3. memoryview CRC — 零拷贝校验
    4. ndarray 池 — 包大小稳定时复用缓冲区
"""

from __future__ import annotations

import struct
import binascii
import numpy as np

from PyQt5.QtCore import (QByteArray, QObject, QThread, Qt, pyqtSignal,
                          pyqtSlot)
from PyQt5.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QSpinBox,
                              QVBoxLayout, QWidget)

from conn_base import ConnNodeContentWidget
from conn_utils import (ThreadManager, disconnectAll,
                        easyDebug, easyInfo, easyWarning, easyError)
from connnodes.waveform_protocol_v3 import decode_raw

# ═══════════════════════════════════════════════════════════════
# 协议常量
# ═══════════════════════════════════════════════════════════════

_FRAME_HEADER: bytes = b"\xAA\x55"      # 帧头
_HEADER_SIZE: int = 2                    # 帧头大小
_DATA_COUNT_OFFSET: int = 7             # 数据数偏移 (uint16 LE)
_BASE_PKT_SIZE: int = 15                # 最小包长度（0 数据点）
_BUFFER_MAX: int = 1_048_576            # 缓冲区上限 1MB


# ═══════════════════════════════════════════════════════════════
# 解析工作线程
# ═══════════════════════════════════════════════════════════════

class _ProtocolParserWorker(QObject):
    """V3 协议解析引擎 — 运行在独立工作线程

    职责: 缓冲区管理、帧头查找、片段重组、CRC-16 校验、
          decode_raw 复用、坏包→gap 转换

    约束:
        1. ★ 必须在独立 QThread 中运行（解析过程可能阻塞）
        2. 使用 read index 指针 _pos 追踪已处理位置而非切片
        3. 缓冲区超过 _BUFFER_MAX 时裁剪前半部分
        4. CRC 校验使用 memoryview 零拷贝
    """

    op_signal = pyqtSignal(int, object, int, int)
    """解析结果输出

    参数:
        - channel_id: int           通道 ID
        - ndarray: object           numpy.ndarray(float64)，含前部 NaN gap
        - gap_count: int            前 N 个点为危险区域
        - interval_us: int          采样间隔微秒
    """

    log_debug = pyqtSignal(str)
    """调试日志（数据详情、缓冲区操作等），由「调试」复选框控制连接"""
    log_info = pyqtSignal(str)
    """信息日志（成功解析事件），由「信息」复选框控制连接"""
    log_warning = pyqtSignal(str)
    """警告日志（坏包、缓冲区溢出等），由「警告」复选框控制连接"""
    log_error = pyqtSignal(str)
    """错误日志（CRC失败、解码异常等），由「错误」复选框控制连接"""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._buffer = bytearray()
        self._pos = 0
        self._np_pool: dict[int, np.ndarray] = {}
        self._channel_offset = 0      # 通道偏移，由主线程配置
        self._ch_count = 1            # 端口数，由主线程配置

    # ── 数据入口 ──────────────────────────────────────────────

    @pyqtSlot(QByteArray)
    def writeData(self, qba: QByteArray) -> None:
        """接收新数据（跨线程槽，由 Qt AutoConnection 投递）"""
        self._buffer.extend(bytes(qba))
        self.log_debug.emit(
            f"协议解析器: 写入 {len(qba)} 字节, 缓冲区 {len(self._buffer)} B")
        self._processBuffer()

    # ── 通道过滤配置 ────────────────────────────────────────

    @pyqtSlot(int, int)
    def setChannelConfig(self, ch_count: int, offset: int) -> None:
        """设置有效通道范围（由主线程在配置变更时调用）

        通道 ID < offset 或 >= offset + ch_count 的包将被跳过，
        不做 CRC 校验和解码。
        """
        self._ch_count = ch_count
        self._channel_offset = offset

    # ── 帧头查找 ────────────────────────────────────────────

    @staticmethod
    def _findHeader(buf: bytearray, start: int = 0,
                    end: int | None = None) -> int:
        """在 buf[start:end] 中查找帧头 0xAA55

        使用 bytes.find()（C 级 memchr），比 Python 逐字节循环快 10-50×
        """
        if end is None:
            end = len(buf)
        return buf.find(_FRAME_HEADER, start, end)

    # ── ndarray 池 ──────────────────────────────────────────

    def _get_np_buffer(self, data_count: int) -> np.ndarray:
        """获取预分配的 ndarray 缓冲区（复用避免分配）"""
        if data_count not in self._np_pool:
            self._np_pool[data_count] = np.empty(data_count, dtype=np.float64)
        return self._np_pool[data_count]

    # ── 核心处理循环 ─────────────────────────────────────────

    def _processBuffer(self) -> None:
        """核心处理循环 — 片段重组 + CRC 校验 + 解码

        性能优化:
            - memoryview 零拷贝 CRC 计算
            - decode_raw 跳过重复校验
            - ndarray 池复用缓冲区
        """
        buf = self._buffer
        pos = self._pos

        while True:
            # 1. 找帧头
            header_pos = self._findHeader(buf, pos)
            if header_pos < 0:
                break

            # 丢弃帧头前的垃圾字节
            if header_pos > pos:
                self.log_debug.emit(
                    f"协议解析器: 帧头搜索 pos={pos} → @{header_pos}")
                pos = header_pos

            # 2. 头部不够完整 — 等更多数据
            if pos + _BASE_PKT_SIZE > len(buf):
                break

            # 3. 解析 data_count → 计算完整包长
            data_count = struct.unpack('<H', buf[pos + _DATA_COUNT_OFFSET:
                                                  pos + _DATA_COUNT_OFFSET + 2])[0]
            pkt_len = _BASE_PKT_SIZE + 4 * data_count

            # 4. 包不完整 — 检查是否有下一帧头
            if pos + pkt_len > len(buf):
                # 在预期包范围内搜索下一帧头
                next_header = self._findHeader(buf, pos + 1, pos + pkt_len)
                if next_header >= 0:
                    self.log_warning.emit(
                        f"协议解析器: ⚠ 帧内发现下一帧头, pos={pos} "
                        f"pkt_len={pkt_len}")
                    # 当前包损坏 → gap，跳到下一帧头
                    self._reportGap(buf, pos)
                    pos = next_header
                    continue
                else:
                    # 等更多数据
                    break

            # 4.5 通道 ID 过滤 — 跳过不属于当前节点的包（不做 CRC 和解码）
            channel_id = buf[pos + 2]
            if not (self._channel_offset <= channel_id <
                    self._channel_offset + self._ch_count):
                self.log_warning.emit(
                    f"协议解析器: ⚠ 通道 {channel_id} 超出范围 "
                    f"(偏移={self._channel_offset}, 端口数={self._ch_count})")
                pos += pkt_len
                continue

            # 5. 完整包 — CRC 校验
            crc_ok = self._check_crc(buf, pos, pkt_len)
            if crc_ok:
                # 快速解码
                try:
                    channel_id, data_np, gap_count, interval_us = \
                        decode_raw(buf, pos, data_count)
                    # 确保 gap 处为 NaN
                    if gap_count > 0:
                        data_np = data_np.copy()
                        data_np[:gap_count] = np.nan
                    elif data_np is not None:
                        # 使用 ndarray 池缓存（仅当不需要 gap 修改时）
                        pool_buf = self._get_np_buffer(data_count)
                        pool_buf[:] = data_np
                        data_np = pool_buf

                    self.log_info.emit(
                        f"协议解析器: ✓ CH{channel_id}  {data_count}点")
                    self.log_debug.emit(
                        f"协议解析器: CH{channel_id}  {data_count}点  "
                        f"gap={gap_count}  interval={interval_us}μs")
                    self.op_signal.emit(channel_id, data_np,
                                        gap_count, interval_us)
                except Exception:
                    self.log_error.emit(
                        f"协议解析器: ✗ 解码异常 pos={pos}")
                    # 解码异常 → gap
                    self._reportGap(buf, pos)
            else:
                # CRC 失败 → gap
                self.log_error.emit(
                    f"协议解析器: ✗ CRC校验失败 pos={pos} "
                    f"pkt_len={pkt_len}")
                self._reportGap(buf, pos)

            pos += pkt_len

        # 6. 更新 _pos
        self._pos = pos

        # 7. 缓冲区裁剪
        if len(buf) > _BUFFER_MAX and self._pos > 0:
            old_size = len(buf)
            del buf[:self._pos]
            self._pos = 0
            self.log_warning.emit(
                f"协议解析器: ⚠ 缓冲区溢出, 裁剪 {old_size} → {len(buf)} B")

    # ── CRC 校验 ────────────────────────────────────────────

    @staticmethod
    def _check_crc(buf: bytearray, pos: int, pkt_len: int) -> bool:
        """CRC-16/CCITT 校验（memoryview 零拷贝）"""
        # 数据部分: 帧头到 CRC 前
        data_view = memoryview(buf)[pos:pos + pkt_len - 2]
        actual_crc = binascii.crc_hqx(data_view, 0xffff)
        # 期望 CRC
        expected_crc = struct.unpack('<H', buf[pos + pkt_len - 2:
                                                pos + pkt_len])[0]
        return actual_crc == expected_crc

    # ── Gap 报告 ────────────────────────────────────────────

    def _reportGap(self, buf: bytearray, pos: int) -> None:
        """报告坏包（CRC 失败或拆包时）

        从 pos 位置解析头部字段构造 gap 包。
        """
        try:
            if pos + _BASE_PKT_SIZE > len(buf):
                return
            channel_id = buf[pos + 2]
            interval_us = struct.unpack('<I', buf[pos+3:pos+7])[0]
            data_count = struct.unpack('<H', buf[pos+7:pos+9])[0]
            gap_count = struct.unpack('<I', buf[pos+9:pos+13])[0]
            total_gap = data_count + gap_count
            self.log_warning.emit(
                f"协议解析器: ⚠ 坏包 CH{channel_id}  {data_count}点  "
                f"gap={gap_count}  interval={interval_us}μs")
        except Exception:
            # 头部解析失败，用默认值
            channel_id = 0
            total_gap = 0
            interval_us = 0
            self.log_warning.emit(
                f"协议解析器: ⚠ 坏包 pos={pos} (头部解析失败)")

        if total_gap > 0:
            gap_data = np.full(total_gap, np.nan, dtype=np.float64)
            self.op_signal.emit(channel_id, gap_data, total_gap, interval_us)


# ═══════════════════════════════════════════════════════════════
# 内容部件（主线程）
# ═══════════════════════════════════════════════════════════════

class ProtocolParserContent(ConnNodeContentWidget):
    """协议解析器 V3 内容部件

    管理: 工作线程生命周期、静态通道信号、UI 控件

    约束:
        1. ch_count 在 __init__ 时确定，运行期间不可更改
        2. ★ ch0~ch3 在类级别声明为 pyqtSignal，
           每个实例按 self._ch_count 使用前 N 个
        3. _channel_offset 影响路由逻辑
        4. 日志复选框使用 disconnectAll 模式（未启用时零开销）
    """

    # ── 类级通道信号（必需：pyqtSignal 必须是类属性才是 pyqtBoundSignal） ──
    ch0 = pyqtSignal(object, int, int)
    ch1 = pyqtSignal(object, int, int)
    ch2 = pyqtSignal(object, int, int)
    ch3 = pyqtSignal(object, int, int)

    def __init__(self, node, ch_count: int,
                 parent: QWidget | None = None) -> None:
        # ── 状态（super().__init__ 前设置，initUI 可能需要） ──
        self._ch_count = ch_count
        self._channel_offset = 0

        # ── 初始化父类 → 触发 initUI 创建 _worker/_thread/UI 控件 ──
        super().__init__(node, parent)

    def initUI(self) -> None:
        """创建 UI 布局和启动工作线程"""
        layout = QVBoxLayout(self)

        # ── 通道偏移 ─────────────────────────────────────
        offset_row = QHBoxLayout()
        offset_label = QLabel("通道偏移", self)
        self.offset_spin = QSpinBox(self)
        self.offset_spin.setRange(0, 255)
        self.offset_spin.setValue(0)
        offset_row.addWidget(offset_label)
        offset_row.addWidget(self.offset_spin)
        offset_row.addStretch()
        layout.addLayout(offset_row)

        # ── 日志选项 ─────────────────────────────────────
        log_label = QLabel("日志选项", self)
        log_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(log_label)

        log_row = QHBoxLayout()
        white_style = "color: white;"
        self.log_error_checkbox = QCheckBox("错误", self)
        self.log_error_checkbox.setChecked(True)
        self.log_error_checkbox.setStyleSheet(white_style)
        self.log_warning_checkbox = QCheckBox("警告", self)
        self.log_warning_checkbox.setChecked(True)
        self.log_warning_checkbox.setStyleSheet(white_style)
        self.log_info_checkbox = QCheckBox("信息", self)
        self.log_info_checkbox.setChecked(False)
        self.log_info_checkbox.setStyleSheet(white_style)
        self.log_debug_checkbox = QCheckBox("调试", self)
        self.log_debug_checkbox.setChecked(False)
        self.log_debug_checkbox.setStyleSheet(white_style)

        log_row.addWidget(self.log_error_checkbox)
        log_row.addWidget(self.log_warning_checkbox)
        log_row.addWidget(self.log_info_checkbox)
        log_row.addWidget(self.log_debug_checkbox)
        layout.addLayout(log_row)

        layout.addStretch()

        # ── 启动工作线程 ─────────────────────────────────
        self._worker = _ProtocolParserWorker()
        self._thread = QThread()
        self._thread.start()
        ThreadManager.instance().register_thread(self._thread)
        self._worker.moveToThread(self._thread)

        # ── 通道过滤配置 ───────────────────────────────
        self._worker.setChannelConfig(self._ch_count, 0)

        # ── 数据路由连接 ────────────────────────────────
        self._worker.op_signal.connect(self._onParsedData)
        self.offset_spin.valueChanged.connect(self._onOffsetChanged)

        # ── 日志复选框初始连接 ──────────────────────────
        self.log_error_checkbox.stateChanged.connect(
            self._logErrorStateChangedHandler)
        self.log_warning_checkbox.stateChanged.connect(
            self._logWarningStateChangedHandler)
        self.log_info_checkbox.stateChanged.connect(
            self._logInfoStateChangedHandler)
        self.log_debug_checkbox.stateChanged.connect(
            self._logDebugStateChangedHandler)

        # 初始同步连接状态
        self._logErrorStateChangedHandler(self.log_error_checkbox.checkState())
        self._logWarningStateChangedHandler(self.log_warning_checkbox.checkState())
        self._logInfoStateChangedHandler(self.log_info_checkbox.checkState())
        self._logDebugStateChangedHandler(self.log_debug_checkbox.checkState())

        self.resize(200, 130)

    # ── 路由 ─────────────────────────────────────────────────

    @pyqtSlot(int, object, int, int)
    def _onParsedData(self, channel_id: int, data_np: np.ndarray,
                      gap_count: int, interval_us: int) -> None:
        """来自 Worker 的解析结果 → 按 channel_id 路由到对应静态端口

        路由公式:
            port_id = channel_id - self._channel_offset
            在范围内 → 对应静态端口 emit
            超出范围 → 日志警告，丢弃
        """
        port_id = channel_id - self._channel_offset
        if 0 <= port_id < self._ch_count:
            getattr(self, f"ch{port_id}").emit(data_np, gap_count, interval_us)
        else:
            easyWarning(
                f"协议解析器: 通道 {channel_id} 超出范围 "
                f"(偏移={self._channel_offset}, 端口数={self._ch_count})"
            )

    # ── 通道偏移 ────────────────────────────────────────────

    @pyqtSlot(int)
    def _onOffsetChanged(self, value: int) -> None:
        """通道偏移值变更（同步 Worker 过滤范围）"""
        self._channel_offset = value
        self._worker.setChannelConfig(self._ch_count, value)

    # ── 分级日志处理（桥接 Worker log 信号 → easyXxx） ───

    @pyqtSlot(str)
    def _logDebugHandler(self, msg: str) -> None:
        easyDebug(msg)

    @pyqtSlot(str)
    def _logInfoHandler(self, msg: str) -> None:
        easyInfo(msg)

    @pyqtSlot(str)
    def _logWarningHandler(self, msg: str) -> None:
        easyWarning(msg)

    @pyqtSlot(str)
    def _logErrorHandler(self, msg: str) -> None:
        easyError(msg)

    # ── 日志复选框状态变更（动态 connect/disconnect）──────

    @pyqtSlot(int)
    def _logDebugStateChangedHandler(self, state: int) -> None:
        if state == Qt.Checked:
            self._worker.log_debug.connect(self._logDebugHandler)
        else:
            disconnectAll(self._worker.log_debug, self._logDebugHandler)

    @pyqtSlot(int)
    def _logInfoStateChangedHandler(self, state: int) -> None:
        if state == Qt.Checked:
            self._worker.log_info.connect(self._logInfoHandler)
        else:
            disconnectAll(self._worker.log_info, self._logInfoHandler)

    @pyqtSlot(int)
    def _logWarningStateChangedHandler(self, state: int) -> None:
        if state == Qt.Checked:
            self._worker.log_warning.connect(self._logWarningHandler)
        else:
            disconnectAll(self._worker.log_warning, self._logWarningHandler)

    @pyqtSlot(int)
    def _logErrorStateChangedHandler(self, state: int) -> None:
        if state == Qt.Checked:
            self._worker.log_error.connect(self._logErrorHandler)
        else:
            disconnectAll(self._worker.log_error, self._logErrorHandler)

    # ── 生命周期 ───────────────────────────────────────────

    def cleanup(self) -> None:
        """清理资源"""
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
            self._thread.deleteLater()
            self._thread = None
