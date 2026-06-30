"""
DataCore — 数据决策核心

双通道数据写入，维护显示缓冲 RingA。
无 Running/Stopped 状态：数据到达即写入，永不丢弃。

线程: 驻留数据决策线程（_DataWorker）。
"""
from __future__ import annotations

import numpy as np
from PyQt5.QtCore import QObject, pyqtSlot

from connnodes.np_ringbuffer import NPRingBuffer


class DataCore(QObject):
    """数据决策核心

    为每个通道维护 RingA（显示环）。
    NPRingBuffer 内部自带锁，外部无需额外保护。
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # ── 双通道显示缓冲 ─────────────────────────
        self._mem_depth = 10000
        self.ring_a: dict[str, NPRingBuffer] = {
            "1": NPRingBuffer(self._mem_depth),
            "2": NPRingBuffer(self._mem_depth),
        }

        # ── 渲染线程可读状态 ────────────────────────
        self.render_state: dict = {"interval_us": 0}

        # ── 主线程 interval_us 容器引用（由 Content 注入）──
        self.interval_us_ref: list | None = None

        # ── 停止接收标志 ───────────────────────────
        self._accept_data = True

    # ── 数据入口（跨线程 slot） ──────────────────

    @pyqtSlot(object, int)
    def on_data_1(self, data: np.ndarray,
                  interval_us: int) -> None:
        """输入 1 数据"""
        if not self._accept_data:
            return
        if "1" in self.ring_a:
            self.ring_a["1"].append(data)
        self.render_state["interval_us"] = interval_us
        if self.interval_us_ref is not None:
            self.interval_us_ref[0] = interval_us

    @pyqtSlot(object, int)
    def on_data_2(self, data: np.ndarray,
                  interval_us: int) -> None:
        """输入 2 数据"""
        if not self._accept_data:
            return
        if "2" in self.ring_a:
            self.ring_a["2"].append(data)
        self.render_state["interval_us"] = interval_us
        if self.interval_us_ref is not None:
            self.interval_us_ref[0] = interval_us

    # ── 参数 Setter ─────────────────────────────

    @pyqtSlot(int)
    def set_mem_depth(self, depth: int) -> None:
        """热装载存储深度：copy 旧数据到新容量 buffer"""
        for ch in ("1", "2"):
            old = self.ring_a[ch].get_range(0, len(self.ring_a[ch]))
            self.ring_a[ch] = NPRingBuffer(depth)
            if len(old) > 0:
                self.ring_a[ch].append(old)
        self._mem_depth = depth

    @pyqtSlot(bool)
    def set_accept_data(self, accept: bool) -> None:
        """停止/恢复接收数据"""
        self._accept_data = accept

    def clear_data(self) -> None:
        """清理 ring buffer（线程安全）：重建新实例"""
        for ch in ("1", "2"):
            self.ring_a[ch] = NPRingBuffer(self._mem_depth)

    def export_data(self) -> dict:
        """导出通道数据 + interval_us（线程安全）"""
        return {
            "interval_us": self.render_state.get("interval_us", 0),
            "ch1": self.ring_a["1"].get_range(0, len(self.ring_a["1"])).tolist(),
            "ch2": self.ring_a["2"].get_range(0, len(self.ring_a["2"])).tolist(),
        }
