"""
示波器核心类 — RingBuffer 和 OscilloscopeSampler（工作线程）

RingBuffer: 环形缓冲区，主线程用于历史数据滚动缓存
OscilloscopeSampler: 简化的工作线程，仅做解码+累积+转发
"""
import math
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QByteArray
from connnodes.waveform_protocol import decode_packet, MAGIC_GAP


class RingBuffer:
    """定长环形缓冲区，存储 float 数据点，追踪覆盖情况"""

    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self._buffer = [0.0] * capacity
        self._write_idx = 0
        self._count = 0
        self._overwrite_count = 0

    @property
    def count(self) -> int:
        """当前有效数据点数"""
        return self._count

    @property
    def overwrite_count(self) -> int:
        """累计覆盖次数（自上次 clear 以来）"""
        return self._overwrite_count

    def write(self, value: float):
        """写入一个数据点，缓冲区满时覆盖旧数据"""
        if self._count == self.capacity:
            self._overwrite_count += 1
        self._buffer[self._write_idx] = value
        self._write_idx = (self._write_idx + 1) % self.capacity
        if self._count < self.capacity:
            self._count += 1

    def write_batch(self, values: list[float]):
        """批量写入原始数据"""
        for v in values:
            self.write(v)

    def copy_state(self):
        """深拷贝当前状态（用于暂停快照）"""
        rb = RingBuffer.__new__(RingBuffer)
        rb.capacity = self.capacity
        rb._buffer = list(self._buffer)
        rb._write_idx = self._write_idx
        rb._count = self._count
        rb._overwrite_count = self._overwrite_count
        return rb

    def clear(self):
        """清空缓冲区，重置所有状态"""
        self._write_idx = 0
        self._count = 0
        self._overwrite_count = 0

    def _get_ordered(self) -> list[float]:
        """返回按时间顺序排列的数据（从最旧到最新）"""
        if self._count == 0:
            return []
        if self._count < self.capacity:
            return self._buffer[:self._count]
        # 环形已满，write_idx 指向最旧数据
        return self._buffer[self._write_idx:] + self._buffer[:self._write_idx]

    def read_frame(self, visible_count: int, scroll_offset: int):
        """读取可见窗口内的数据快照

        Args:
            visible_count: 希望获取的数据点数
            scroll_offset: 从最新数据向历史方向的偏移量（0=最新）

        Returns:
            (data, overwrite_count, scrollbar_max, frame_start)
            frame_start: 返回数据在 ordered 中的起始索引
        """
        ordered = self._get_ordered()
        total = len(ordered)

        if total == 0:
            return [], self._overwrite_count, 0, 0

        vc = min(visible_count, total)
        scrollbar_max = total - vc
        actual_offset = min(scroll_offset, scrollbar_max)

        start = scrollbar_max - actual_offset  # scroll_offset=0 → 显示最新
        start = max(0, start)
        data = ordered[start:start + vc]

        return data, self._overwrite_count, scrollbar_max, start

    def resize(self, new_capacity: int):
        """调整缓冲区大小，尽可能保留已有数据"""
        if new_capacity == self.capacity:
            return

        ordered = self._get_ordered()

        self._buffer = [0.0] * new_capacity
        self._write_idx = 0
        self._count = 0
        self.capacity = new_capacity
        self._overwrite_count = 0

        for val in ordered:
            if self._count >= new_capacity:
                break
            self._buffer[self._write_idx] = val
            self._write_idx = (self._write_idx + 1) % new_capacity
            self._count += 1


class OscilloscopeSampler(QObject):
    """
    示波器采样器 — 工作线程核心（简化版）

    工作线程不再管理历史数据。只维护一个小型临时缓冲区，
    累积分帧间的数据点，定时器到时发射给主线程后清空。

    信号：
        frameReady(data, gap_count, sampling_interval_us)
            data: float 列表（原始数据，未应用 amp/offset）
            gap_count: 临时缓冲区溢出丢弃的点数（= 不可信区域大小）
            sampling_interval_us: 当前采样间隔（微秒/点）
    """
    frameReady = pyqtSignal(list, int, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 临时累积缓冲区（帧间缓存，秒级以下）
        self._temp_rb = RingBuffer(5000)
        # 帧定时器
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._onFrameTick)
        self._fps = 30
        # 渲染保护
        self._awaiting_render = False
        self._running = False
        # 从协议包获取的采样间隔
        self._sampling_interval_us = 1000

    # ── 公共槽（可跨线程调用） ─────────────────────────────

    def _processWaveformData(self, points: list[float], interval_us: int, gap_count: int):
        """将原始波形数据写入临时缓冲区（公共处理逻辑）

        Args:
            points: 全部数据点（含前部 gap 点）
            interval_us: 采样间隔（微秒）
            gap_count: 头部 gap 点数
        """
        if interval_us > 0:
            self._sampling_interval_us = interval_us
        clean_data = points[gap_count:]
        if clean_data:
            self._temp_rb.write_batch(clean_data)

    @pyqtSlot(QByteArray)
    def writeData(self, data: QByteArray):
        """接收协议包，解码后写入临时累积缓冲区"""
        packet = decode_packet(data)
        if packet is None:
            return
        self._processWaveformData(
            packet["data"],
            packet["sampling_interval_us"],
            packet["gap_count"],
        )

    @pyqtSlot(dict)
    def writeJsonData(self, data: dict):
        """接收 dict 格式的波形数据，直接写入临时缓冲区

        Dict 格式: {"点": [...], "采样间隔_us": int, "gap数": int}
        """
        self._processWaveformData(
            data.get("点", []),
            data.get("采样间隔_us", 1000),
            data.get("gap数", 0),
        )

    @pyqtSlot()
    def start(self):
        """启动帧定时器"""
        self._running = True
        self._frame_timer.start(1000 // self._fps)

    @pyqtSlot()
    def stop(self):
        """停止帧定时器，发射剩余数据（如有）"""
        self._running = False
        self._frame_timer.stop()

        # 停止前进驻剩余数据
        self._flushBuffer()

    @pyqtSlot()
    def onRenderComplete(self):
        """主线程渲染完成通知 → 解除背压，允许下一帧"""
        self._awaiting_render = False

    @pyqtSlot()
    def clear(self):
        """清空临时累积缓冲区"""
        self._temp_rb.clear()

    @pyqtSlot(int)
    def setTempBufferSize(self, size: int):
        """调整临时缓冲区容量（保留已有数据）"""
        self._temp_rb.resize(max(100, size))

    @pyqtSlot(int)
    def setFps(self, fps: int):
        """设置帧率"""
        self._fps = max(1, min(fps, 120))
        if self._running:
            self._frame_timer.setInterval(1000 // self._fps)

    # ── 内部 ─────────────────────────────────────────────

    def _flushBuffer(self):
        """读取临时缓冲区的所有数据并发射，然后清空

        gap_count = 缓冲区满后被覆盖的点数。
        如果 gap_count > 0，在数据前部插入 gap_count 个 NaN 魔法数字，
        画板检测到 NaN 后绘制为红色危险线段。
        """
        if self._temp_rb.count == 0:
            return

        data, gap_count, _, _ = self._temp_rb.read_frame(10 ** 9, 0)
        self._temp_rb.clear()

        # gap_count > 0 → 数据前插入 NaN 魔法数字
        if gap_count > 0:
            data = [MAGIC_GAP] * gap_count + data

        # gap_count > 0 表示有数据被覆盖（不可信）
        self._awaiting_render = True
        self.frameReady.emit(data, gap_count, self._sampling_interval_us)

    def _onFrameTick(self):
        """帧定时器回调 — 渲染保护通过则发射一帧"""
        if self._awaiting_render or not self._running:
            return
        self._flushBuffer()
