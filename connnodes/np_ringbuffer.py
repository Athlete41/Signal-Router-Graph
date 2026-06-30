"""
numpy 环形缓冲区 —— 头尾指针 + get 索引重映射

自带 QMutex，内部加锁，外部调用者无需关心。
append/write 加锁, get_range/read 加锁, 同一时间只一个线程进。
"""

import numpy as np
from PyQt5.QtCore import QMutex, QMutexLocker


class NPRingBuffer:
    def __init__(self, capacity=10000):
        self._buf = np.empty(capacity, dtype=np.float32)
        self._cap = capacity
        self._pos = 0
        self._count = 0
        self._write_count = 0
        self._mutex = QMutex(QMutex.Recursive)

    def append(self, data: np.ndarray):
        with QMutexLocker(self._mutex):
            n = len(data)
            if n == 0:
                return
            if n >= self._cap:
                self._buf[:] = data[-self._cap:]
                self._pos = 0
                self._count = self._cap
                self._write_count += 1
                return

            space = self._cap - self._pos
            if n <= space:
                self._buf[self._pos:self._pos + n] = data
            else:
                self._buf[self._pos:] = data[:space]
                self._buf[:n - space] = data[space:]

            self._pos = (self._pos + n) % self._cap
            self._count = min(self._count + n, self._cap)

            self._write_count += 1

    def get_range(self, start: int, count: int) -> np.ndarray:
        with QMutexLocker(self._mutex):
            n = len(self)
            if n == 0:
                return np.array([], dtype=np.float32)

            if start < 0:
                start += n
            start = max(0, min(start, n - 1))
            count = max(0, min(count, n - start))
            if count == 0:
                return np.array([], dtype=np.float32)

            if self._count < self._cap:
                return self._buf[start:start + count].copy()

            # 已回绕
            phys = (self._pos + start) % self._cap
            if phys + count <= self._cap:
                return self._buf[phys:phys + count].copy()
            first = self._cap - phys
            return np.concatenate([
                self._buf[phys:],
                self._buf[:count - first]
            ])

    def __len__(self):
        return min(self._count, self._cap)

    def get_write_count(self) -> int:
        return self._write_count

    def __repr__(self):
        return (f"NPRingBuffer(cap={self._cap}, "
                f"pos={self._pos}, len={min(self._count, self._cap)})")
