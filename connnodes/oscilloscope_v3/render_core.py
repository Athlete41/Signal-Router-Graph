"""
RenderCore — 渲染帧核心

从 RingA 读取窗口数据，降采样（逐桶 min-max），映射到屏幕坐标。
直接构建 QPainterPath 写入 WaveformView 的 pending_path，通过双缓冲交换。

线程: 驻留渲染帧线程（_RenderWorker）。
"""
from __future__ import annotations

import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QPainterPath
import math


class RenderCore(QObject):
    """渲染帧核心

    通过外部 RingA 引用读取数据，直接构建 QPainterPath。
    """

    waveform_ready = pyqtSignal(int, int, int)
    # start, total_pts, window_pt

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ring_a_ref: dict | None = None   # DataCore.ring_a 的引用

        # WaveformView 引用（由 Content init 时注入）
        self._waveform_view: WaveformView | None = None

        # ── QPainterPath 缓存 ──
        self._cached_path_1: QPainterPath | None = None
        self._cached_path_2: QPainterPath | None = None
        self._cached_key: tuple | None = None
        self._debug_method: tuple | None = None
        
    # ── 渲染入口 ────────────────────────────────

    @pyqtSlot(object)
    def on_render_request(self, params: dict) -> None:
        """
        params 键名参考 总体.md 四的用户参数表：
            x_window_ms, x_scroll,
            y_window_mv_1, y_offset_mv_1,
            y_window_mv_2, y_offset_mv_2,
            screen_w, screen_h, interval_us
        """
        if self.ring_a_ref is None or self._waveform_view is None:
            return

        interval_us = params["interval_us"]
        if interval_us <= 0:
            self.waveform_ready.emit(0, 0, 0)
            return

        window_linecount = params["x_window_ms"] * 1000 / interval_us
        window_pt = math.ceil(window_linecount) + 1

        # 总点数（取两通道最长）
        total_pts = max(len(self.ring_a_ref.get("1", [])),
                        len(self.ring_a_ref.get("2", [])))

        # x_scroll: None=自动滚动, int=手动位置
        x_scroll = params.get("x_scroll", None)
        if x_scroll is None:
            start = max(0, total_pts - window_pt)
        else:
            start = max(0, min(x_scroll, total_pts - window_pt))


        # 检查缓存
        ring_1 = self.ring_a_ref.get("1")
        ring_2 = self.ring_a_ref.get("2")
        wc1 = ring_1.get_write_count()
        wc2 = ring_2.get_write_count()

        if self._check_cache(params, wc1, wc2):
        # if self._check_cache(params, wc1, wc2) and False:
            # 缓存命中
            # ⚠️ 跨线程写 pending_path，安全依赖数据链路协议，见下方同款注释
            self._waveform_view.pending_path_1 = self._cached_path_1
            self._waveform_view.pending_path_2 = self._cached_path_2
            self.waveform_ready.emit(start, total_pts, window_pt)
        else:
            # 缓存未命中
            data_1 = ring_1.get_range(start, window_pt)
            data_2 = ring_2.get_range(start, window_pt)

            screen_w = params["screen_w"]
            screen_h = params["screen_h"]
            cy = screen_h / 2.0

            half_v_1 = params["y_window_mv_1"] / 1000 / 2.0
            off_v_1 = params["y_offset_mv_1"] / 1000
            half_v_2 = params["y_window_mv_2"] / 1000 / 2.0
            off_v_2 = params["y_offset_mv_2"] / 1000


            path1, method1 = self._build_path(data_1, half_v_1, off_v_1, cy,
                                    screen_w, window_linecount)
            path2, method2 = self._build_path(data_2, half_v_2, off_v_2, cy,
                                    screen_w, window_linecount)
            
            # ⚠️ 跨线程写 WaveformView.pending_path（渲染线程→主线程对象）
            # 安全前提（数据链路协议）：
            #   1. WaveformView 发 render_request 时置 _render_busy=True
            #   2. RenderCore 处理完才 emit waveform_ready（QueuedConnection）
            #   3. 主线程 on_render_path 收到后：
            #      a) 交换 pending↔active（主线程写 path_1/2）
            #      b) 置 _render_busy=False
            #   4. 下一个 tick 检查 _render_busy，为 True 则跳过不发请求
            # → 任意时刻最多一个线程持有 pending_path 的写权限，
            #   paintEvent 只读 path_1/2（active），从不读 pending_path。
            #   不存在并发读写同一字段的时间窗口。
            self._waveform_view.pending_path_1 = path1
            self._waveform_view.pending_path_2 = path2

            self.waveform_ready.emit(start, total_pts, window_pt)

            # 缓存
            self._write_cache(params, wc1, wc2, path1, path2)

            # 调试信息
            self._debug_method = (method1, method2)

    # ── 路径构建 ────────────────────────────────

    @staticmethod
    def _build_path(data: np.ndarray,
                    half_v: float, off_v: float,
                    cy: float,
                    screen_w: int, window_linecount: float) -> tuple[QPainterPath | None, str]:
        """构建 QPainterPath

        两种模式:
          k <= 3  : 直接模式，每个点按时间比例定位
          k >  3  : 降采样模式，每像素一个桶画竖线
        """
        path = QPainterPath()
        method = None

        if window_linecount / screen_w <= 3:
            # 直接模式：不降采样，每个点按时间比例定位
            px_per_pt = screen_w / window_linecount  # 每个数据点占多少像素
            started = False
            for i in range(len(data)):
                val = float(data[i])
                if np.isnan(val):
                    started = False
                    continue
                y = RenderCore._y(val, half_v, off_v, cy)
                x = i * px_per_pt
                if not started:
                    path.moveTo(x, y)
                    started = True
                else:
                    path.lineTo(x, y)
            method = "direct"
        else:
            # 降采样模式：三个数组，单路径编织
            #   主体 → max → min → 回主体 → 下一个主体（全程一个子路径）
            k = round(window_linecount / screen_w + 1)
            data_max, data_min = RenderCore.downsample_peak(data, k)
            data_normal = RenderCore.downsample(data, k)

            started = False
            for i in range(len(data_normal)):
                val_max, val_min = float(data_max[i]), float(data_min[i])
                if np.isnan(val_max) or np.isnan(val_min):
                    started = False
                    continue

                val = float(data_normal[i])
                y = RenderCore._y(val, half_v, off_v, cy)

                # 主体连线（连接到当前桶 body 点）
                if not started:
                    path.moveTo(i, y)
                    started = True
                else:
                    path.lineTo(i, y)

                # 编织毛刺：body → max → min → body（全部 lineTo，保持子路径连续）
                y_max = RenderCore._y(val_max, half_v, off_v, cy)
                y_min = RenderCore._y(val_min, half_v, off_v, cy)
                path.lineTo(i, y_max)
                path.lineTo(i, y_min)
                path.lineTo(i, y)

            method = "downsample_peak"

        if path.elementCount() == 0:
            return None, method
        
        return path, method

    # ── 降采样 + 坐标映射 ──────────────────────

    def _check_cache(self, params: dict, wc1, wc2) -> bool:
        """检查缓存键"""
        return (params["x_window_ms"], params.get("x_scroll", None),
               params["y_window_mv_1"], params["y_offset_mv_1"],
               params["y_window_mv_2"], params["y_offset_mv_2"],
               params["screen_w"], params["screen_h"],
               params["interval_us"], wc1, wc2) == self._cached_key


    def _write_cache(self, params: dict, wc1, wc2, path1, path2):
        """写缓存键"""
        self._cached_key = (params["x_window_ms"], params.get("x_scroll", None),
                           params["y_window_mv_1"], params["y_offset_mv_1"],
                           params["y_window_mv_2"], params["y_offset_mv_2"],
                           params["screen_w"], params["screen_h"],
                           params["interval_us"], wc1, wc2)
        
        self._cached_path_1 = path1
        self._cached_path_2 = path2

    @staticmethod
    def downsample(data: np.ndarray, k: int) -> np.ndarray:
        """普通降采样，每 k 个点取一个（步进采样）"""
        n = len(data)
        M = n // k
        if M == 0:
            return np.array([], dtype=data.dtype)
        return data[:M * k:k]

    @staticmethod
    def downsample_peak(data: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
        """峰值降采样，返回 (max, min) 各 M 个（向量化）"""
        n = len(data)
        M = n // k
        if M == 0:
            return np.array([], dtype=data.dtype), np.array([], dtype=data.dtype)
        reshaped = data[:M * k].reshape(M, k)  # 零拷贝 view
        data_max = np.max(reshaped, axis=1)
        data_min = np.min(reshaped, axis=1)
        return data_max, data_min

    @staticmethod
    def _y(val: float, half_v: float, off_v: float,
           cy: float) -> float:
        """电压值 → 屏幕 y 坐标"""
        return cy - (val - off_v) / half_v * cy
