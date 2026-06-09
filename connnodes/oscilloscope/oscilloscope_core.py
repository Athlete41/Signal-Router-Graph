"""
示波器核心类 — RingBuffer 和 OscilloscopeSampler（工作线程）

OscilloscopeSampler 接收 QByteArray 协议包，在工作线程中完成：
  协议解析 → 写入环形缓冲区（原始数据）
  按时间窗口 → 可见数据窗口 → 应用放大/偏移 → 帧发送
"""
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QByteArray
from connnodes.waveform_protocol import decode_packet


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

    def write(self, value: float):
        """写入一个数据点，缓冲区满时覆盖旧数据"""
        if self._count == self.capacity:
            self._overwrite_count += 1
        self._buffer[self._write_idx] = value
        self._write_idx = (self._write_idx + 1) % self.capacity
        if self._count < self.capacity:
            self._count += 1

    def write_batch(self, values: list[float]):
        """批量写入原始数据（不在此处应用放大/偏移，由 _emitFrame 统一处理）"""
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

    def _compute_ov_region(self, total: int, start: int, data_len: int):
        """计算数据切片内的覆盖区域边界

        覆盖区域 = ordered 视图末尾的 min(overwrite_count, total) 个元素，
        因为这些位置的数据是通过覆盖旧数据写入的。

        Returns:
            () 或 (min_idx, max_idx) 在 data 切片内的索引
        """
        if self._overwrite_count == 0 or total == 0:
            return ()
        n_ov = min(self._overwrite_count, total)          # 被覆盖过的元素数
        ov_ordered_min = total - n_ov                      # 覆盖区域起点 (ordered 坐标)
        ov_ordered_max = total - 1                         # 覆盖区域终点 (= 缓冲区末尾)

        # 转换到 data 切片内的坐标
        ov_min_data = ov_ordered_min - start
        ov_max_data = ov_ordered_max - start

        # 只要任一边界在可见范围内就显示
        if ov_min_data < 0 and ov_max_data < 0:
            return ()  # 完全在可见区域左侧
        if ov_min_data >= data_len and ov_max_data >= data_len:
            return ()  # 完全在可见区域右侧

        ov_min_data = max(0, min(ov_min_data, data_len - 1))
        ov_max_data = max(0, min(ov_max_data, data_len - 1))
        return (ov_min_data, ov_max_data)

    def read_frame(self, visible_count: int, scroll_offset: int):
        """读取可见窗口内的数据快照

        Args:
            visible_count: 希望获取的数据点数
            scroll_offset: 从最新数据向历史方向的偏移量（0=最新）

        Returns:
            (data, overwrite_count, overwrite_region, scrollbar_max)
            overwrite_region 为 () 表示无覆盖，或 (min, max) 为数据切片内的索引
        """
        ordered = self._get_ordered()
        total = len(ordered)

        if total == 0:
            return [], self._overwrite_count, (), 0

        vc = min(visible_count, total)                    # 不超过已有数据
        scrollbar_max = total - vc                         # 滚动条最大值
        actual_offset = min(scroll_offset, scrollbar_max)  # 钳位

        start = scrollbar_max - actual_offset  # scroll_offset=0 → 显示最新
        start = max(0, start)
        data = ordered[start:start + vc]
        data_len = len(data)

        ov_region = self._compute_ov_region(total, start, data_len)

        return data, self._overwrite_count, ov_region, scrollbar_max

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
    示波器采样器 — 工作线程核心

    接收 QByteArray 协议包 → 解析 → 放大/偏移 → 写入环形缓冲区。
    支持时间窗口控制和历史滚动查看。

    信号：
        frameReady(data, overwrite_count, overwrite_region, ms_per_div, scrollbar_max)
    """
    frameReady = pyqtSignal(list, int, object, float, int)

    # 网格划分数量（用于计算 ms/div）
    GRID_DIVISIONS = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ring_buffer = RingBuffer(10000)
        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._onFrameTick)
        self._fps = 30
        self._amplification = 1.0
        self._offset = 0.0
        self._awaiting_render = False
        self._running = False
        self._snapshot: RingBuffer | None = None  # 暂停时的缓冲区快照

        # 时间窗口与滚动
        self._time_window_s = 1.0                # 默认显示 1 秒
        self._sampling_interval_us = 1000        # 默认 1ms（没有数据时）
        self._scrollbar_value = 10 ** 9          # 初始极大值，自动跟随最新

    # ── 内部计算 ───────────────────────────────────────────────

    def _calc_visible_count(self, buf: RingBuffer | None = None) -> int:
        """根据时间窗口和采样间隔计算可见数据点数"""
        buf = buf or self._ring_buffer
        if self._sampling_interval_us <= 0:
            return buf.count
        count = int(self._time_window_s * 1_000_000 / self._sampling_interval_us)
        return max(1, min(count, buf.capacity))

    def _calc_ms_per_div(self, visible_count: int) -> float:
        """计算每格对应多少毫秒"""
        if visible_count <= 0 or self._sampling_interval_us <= 0:
            return 0.0
        total_time_us = visible_count * self._sampling_interval_us
        return total_time_us / 1000.0 / self.GRID_DIVISIONS

    def _get_scroll_offset(self, total: int, visible_count: int) -> int:
        """将滚动条值转换为 scroll_offset（0=最新）"""
        max_offset = max(0, total - visible_count)
        sb_val = min(self._scrollbar_value, max_offset)
        return max_offset - sb_val

    # ── 槽函数（可被跨线程调用） ──────────────────────────────

    @pyqtSlot(QByteArray)
    def writeData(self, data: QByteArray):
        """接收 QByteArray 协议包，解析后写入环形缓冲区（原始数据，不在此处应用 amp/offset）"""
        packet = decode_packet(data)
        if packet is None:
            return

        # 从协议包更新采样间隔
        if packet["sampling_interval_us"] > 0:
            self._sampling_interval_us = packet["sampling_interval_us"]

        self._ring_buffer.write_batch(packet["data"])

    @pyqtSlot(int)
    def setFps(self, fps: int):
        """设置帧率"""
        self._fps = max(1, min(fps, 120))
        if self._running:
            self._frame_timer.setInterval(1000 // self._fps)

    @pyqtSlot(int)
    def setBufferSize(self, size: int):
        """设置缓冲区大小"""
        self._ring_buffer.resize(max(100, size))
        self._snapshot = None  # 快照失效
        # 暂停时重新发射以反映新大小
        if not self._running and not self._awaiting_render:
            self._emitFrame()

    @pyqtSlot(float)
    def setAmplification(self, amp: float):
        """设置放大倍数"""
        self._amplification = amp
        # 暂停时立即用新倍数重新渲染
        if not self._running and not self._awaiting_render:
            self._emitFrame()

    @pyqtSlot(float)
    def setOffset(self, offset: float):
        """设置偏移量"""
        self._offset = offset
        # 暂停时立即用新偏移重新渲染
        if not self._running and not self._awaiting_render:
            self._emitFrame()

    @pyqtSlot(float)
    def setTimeWindow(self, seconds: float):
        """设置时间窗口（秒）"""
        self._time_window_s = max(0.01, seconds)
        # 暂停时立即用新窗口重新渲染
        if not self._running and not self._awaiting_render:
            self._emitFrame()

    @pyqtSlot(int)
    def setScrollPos(self, value: int):
        """设置滚动条位置（0=最旧，增大=更新）"""
        self._scrollbar_value = max(0, value)
        # 暂停状态下拖滚动条 → 立即发射一帧
        if not self._running and not self._awaiting_render:
            self._emitFrame()

    @pyqtSlot()
    def clear(self):
        """清空缓冲区，立即发射空帧"""
        self._ring_buffer.clear()
        self._snapshot = None
        self._sampling_interval_us = 1000
        self._scrollbar_value = 10 ** 9
        self.frameReady.emit([], 0, (), 0.0, 0)

    @pyqtSlot()
    def start(self):
        """启动帧定时器"""
        self._snapshot = None
        self._running = True
        self._frame_timer.start(1000 // self._fps)

    @pyqtSlot()
    def stop(self):
        """停止帧定时器，冻结缓冲区快照，发射最终帧保持显示"""
        self._running = False
        self._frame_timer.stop()
        self._snapshot = self._ring_buffer.copy_state()
        if not self._awaiting_render:
            self._emitFrame()

    @pyqtSlot()
    def onRenderComplete(self):
        """主线程渲染完成通知"""
        self._awaiting_render = False

    # ── 内部 ───────────────────────────────────────────────

    def _emitFrame(self):
        """计算并发射一帧（无渲染保护，仅内部调用）

        amp/offset 在此处统一应用（不在 writeData 时固化），
        因此暂停状态下调放大倍数/偏移会立即生效。
        """
        buf = self._snapshot if (not self._running and self._snapshot is not None) else self._ring_buffer
        vc = self._calc_visible_count(buf)
        scroll_offset = self._get_scroll_offset(buf.count, vc)
        data, ov_count, ov_region, scrollbar_max = \
            buf.read_frame(vc, scroll_offset)

        # 在读取后统一应用放大倍数和偏移（buffer 中只存原始数据）
        if self._amplification != 1.0 or self._offset != 0.0:
            data = [v * self._amplification + self._offset for v in data]

        ms_per_div = self._calc_ms_per_div(len(data))

        self._awaiting_render = True
        self.frameReady.emit(data, ov_count, ov_region,
                             ms_per_div, scrollbar_max)

    def _onFrameTick(self):
        """帧定时器回调 — 渲染保护通过则发射一帧"""
        if self._awaiting_render:
            return
        self._emitFrame()
