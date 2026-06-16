"""
示波器 V3 — Schmitt 触发检测

纯 NumPy 实现，在 Worker 线程运行。包含触发配置类和检测函数。

算法流程:
    原始数据 → 二值化（Schmitt 滞回比较）→ 边沿检测 → 消抖 → 触发索引
"""

from __future__ import annotations

import numpy as np


# ═══════════════════════════════════════════════════════════════
# 触发配置
# ═══════════════════════════════════════════════════════════════

class TriggerConfig:
    """触发配置（权威值归 Worker 线程所有）

    字段:
        enabled (bool): 触发启闭
        mode (str): "auto" — 有触发对齐/无触发显示最新
                    "normal" — 仅触发时更新
        edge (str): "rising"/"falling"/"both"
        high_thresh (float): 高阈值
        low_thresh (float): 低阈值
        debounce_samples (int): 消抖窗口大小
    """

    def __init__(self) -> None:
        self.enabled = False
        self.mode = "auto"
        self.edge = "rising"
        self.high_thresh = 1.0
        self.low_thresh = -1.0
        self.debounce_samples = 5

    def copy_from(self, other: "TriggerConfig") -> None:
        """从另一个配置复制所有字段"""
        self.enabled = other.enabled
        self.mode = other.mode
        self.edge = other.edge
        self.high_thresh = other.high_thresh
        self.low_thresh = other.low_thresh
        self.debounce_samples = other.debounce_samples


# ═══════════════════════════════════════════════════════════════
# 算法函数
# ═══════════════════════════════════════════════════════════════

def _schmitt_binarize(data: np.ndarray,
                      high: float, low: float) -> np.ndarray:
    """Schmitt 滞回二值化

    高于 high → 1，低于 low → 0，介于之间保持前值（滞回效应）。

    由于滞回区依赖前值（串行依赖），无法纯向量化，用 Python 循环。
    数据量 ≈ 可见窗口大小（≤ screen_w 量级），循环开销可忽略。
    """
    n = len(data)
    if n == 0:
        return np.array([], dtype=np.int8)

    binary = np.zeros(n, dtype=np.int8)
    state = 0
    for i in range(n):
        v = data[i]
        if v >= high:
            state = 1
        elif v <= low:
            state = 0
        binary[i] = state
    return binary


def _detect_edges(binary: np.ndarray, edge: str) -> np.ndarray:
    """检测边沿位置

    Args:
        binary: 二值化序列（0/1）
        edge: "rising" / "falling" / "both"

    Returns:
        边沿在原始数组中的索引（升序）
    """
    diff = np.diff(binary)
    if edge == "rising":
        edges = np.where(diff == 1)[0] + 1
    elif edge == "falling":
        edges = np.where(diff == -1)[0] + 1
    else:  # "both"
        edges = np.where(np.abs(diff) == 1)[0] + 1
    return edges


def _debounce(edges: np.ndarray, debounce_samples: int) -> np.ndarray:
    """滑动窗口消抖

    检测到一个边沿后，后续 debounce_samples 个点内的所有边沿被丢弃。
    """
    if len(edges) == 0:
        return edges

    filtered = [edges[0]]
    for e in edges[1:]:
        if e - filtered[-1] >= debounce_samples:
            filtered.append(e)

    return np.array(filtered, dtype=int)


def detect_trigger(data: np.ndarray, config: TriggerConfig) -> int:
    """检测触发点

    Args:
        data: 波形数据窗口 (float64 ndarray)
        config: 触发配置

    Returns:
        触发点在 data 中的索引，未找到返回 -1
    """
    if not config.enabled or len(data) == 0:
        return -1

    binary = _schmitt_binarize(data, config.high_thresh, config.low_thresh)
    edges = _detect_edges(binary, config.edge)

    if len(edges) == 0:
        return -1

    debounced = _debounce(edges, config.debounce_samples)
    if len(debounced) == 0:
        return -1

    return int(debounced[0])
