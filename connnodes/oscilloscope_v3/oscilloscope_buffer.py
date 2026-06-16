"""
NumpyRingBuffer — 预分配 numpy 环形缓冲区

用于示波器 V3 的每通道 Worker，缓存历史波形数据。

容量可通过构造参数配置（默认 100 万点），但一旦创建后不支持运行时
动态扩容（需要扩容时创建新实例后调用 clear）。
"""

from __future__ import annotations

import numpy as np


class NumpyRingBuffer:
    """环形缓冲区，预分配 float64 ndarray，支持回绕写入和按序读取。

    字段:
        _buffer (ndarray): shape=(capacity,) 的环形存储
        _write_idx (int): 当前写入位置（环形索引）
        _count (int): 已写入总点数（≤ capacity）
        _capacity (int): 缓冲区容量
    """

    def __init__(self, capacity: int = 1_000_000) -> None:
        self._capacity = capacity
        self._buffer = np.empty(capacity, dtype=np.float64)
        self._write_idx = 0
        self._count = 0

    # ── 写入 ──────────────────────────────────────────────────

    def write_batch(self, data: np.ndarray) -> int:
        """批量写入，自动回绕。

        数据量超过容量时只保留最后 capacity 个点。
        缓冲区未满时写入空闲位置，已满时覆盖最旧的数据。

        Args:
            data: float64 ndarray

        Returns:
            被覆盖的旧数据点数（= 0 表示无覆盖，> 0 有数据丢失）
        """
        n = len(data)
        if n == 0:
            return 0

        old_count = self._count

        # 数据超容量时截断
        if n > self._capacity:
            data = data[-self._capacity:]
            n = self._capacity

        # 分段写入（处理回绕）
        space = self._capacity - self._write_idx
        if n <= space:
            self._buffer[self._write_idx:self._write_idx + n] = data
        else:
            self._buffer[self._write_idx:] = data[:space]
            self._buffer[:n - space] = data[space:]

        # 更新状态
        self._write_idx = (self._write_idx + n) % self._capacity
        self._count = min(old_count + n, self._capacity)

        return max(0, old_count + n - self._capacity)

    # ── 读取 ──────────────────────────────────────────────────

    def read_frame(self, visible_count: int,
                   scroll_offset: int = 0) -> tuple:
        """从缓冲区尾部偏移后读取可见窗口。

        逻辑上从「尾部 - scroll_offset」位置开始，向前读 visible_count 个点。
        scroll_offset = 0 时返回最新数据。

        Args:
            visible_count: 想要读取的点数
            scroll_offset: 从尾部往前偏移的点数

        Returns:
            (data, start_idx, actual_count):
                - data: float64 ndarray（零拷贝 view 或拼接数组）
                - start_idx: 数据在缓冲区中的起始逻辑索引
                - actual_count: 实际返回的点数（≤ visible_count）
        """
        if self._count == 0:
            return (np.array([], dtype=np.float64), 0, 0)

        end = self._count
        start = max(0, end - visible_count - scroll_offset)
        actual = min(visible_count, end - start)

        if actual <= 0:
            return (np.array([], dtype=np.float64), 0, 0)

        data = self._ordered_slice(start, actual)
        return (data, start, actual)

    def _ordered_slice(self, start: int, count: int) -> np.ndarray:
        """按逻辑顺序读取连续数据段。

        缓冲区未回绕时返回零拷贝 view，已回绕时拼接。
        """
        if count <= 0:
            return np.array([], dtype=np.float64)

        if self._count < self._capacity:
            # 未回绕 — 数据连续存储在 buffer[0:_count]
            return self._buffer[start:start + count].copy()
        else:
            # 已回绕 — 逻辑顺序: buffer[_write_idx:] + buffer[:_write_idx]
            phys_start = (self._write_idx + start) % self._capacity
            phys_end = (self._write_idx + start + count) % self._capacity

            if phys_start < phys_end:
                return self._buffer[phys_start:phys_end].copy()
            else:
                # 跨越回绕边界 → 拼接
                return np.concatenate([
                    self._buffer[phys_start:],
                    self._buffer[:phys_end]
                ])

    # ── 生命周期 ────────────────────────────────────────────

    def clear(self) -> None:
        """清空缓冲区（重置写指针和计数）"""
        self._write_idx = 0
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    @property
    def capacity(self) -> int:
        return self._capacity

    def __repr__(self) -> str:
        return (f"NumpyRingBuffer(capacity={self._capacity}, "
                f"count={self._count}, write_idx={self._write_idx})")
