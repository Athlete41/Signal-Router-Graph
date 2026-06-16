"""
示波器 V3 — OscilloscopeSampler（每通道 Worker）

每个通道一个实例，运行在独立 QThread 中。
职责:
    1. 接收解析器数据 → 写入 NumpyRingBuffer
    2. QTimer 按 FPS 驱动帧计算
    3. 从 RingBuffer 读取可见窗口 → 降采样包络（min/max）
    4. 可选触发检测（Scmitt 触发）
    5. 包络结果写入共享变量，供主线程 WaveformWidget 读取
"""

from __future__ import annotations

import numpy as np
from PyQt5.QtCore import (QObject, QTimer, pyqtSignal, pyqtSlot)

from .oscilloscope_buffer import NumpyRingBuffer
from .oscilloscope_trigger import TriggerConfig, detect_trigger


class OscilloscopeSampler(QObject):
    """每通道采样/包络计算 Worker（运行在独立 QThread）

    共享变量（Worker 写，主线程只读）:
        _envelope_vmin (ndarray): 下包络数组
        _envelope_vmax (ndarray): 上包络数组（降采样时 ≠ vmin）
        _envelope_write_offset (int): 包络对应的 RingBuffer 偏移

    配置参数（通过信号从主线程跨线程设置）:
        sig_set_* 信号 → 对应 _set* 槽函数
    """

    # ── 常量 ────────────────────────────────────────────────
    ENVELOPE_MARGIN = 2.0   # 包络缓存倍率（>1 供拖拽缓冲）

    # ── 控制信号（主线程 emit → Worker 线程执行） ──────────
    sig_set_sample_rate = pyqtSignal(float)
    sig_set_time_window = pyqtSignal(float)
    sig_set_scroll_offset = pyqtSignal(int)
    sig_set_screen_w = pyqtSignal(int)
    sig_set_running = pyqtSignal(bool)
    sig_set_fps = pyqtSignal(int)
    sig_set_paused = pyqtSignal(bool)

    # 触发配置
    sig_set_upper_threshold = pyqtSignal(float)
    sig_set_lower_threshold = pyqtSignal(float)
    sig_set_trigger_enabled = pyqtSignal(bool)
    sig_set_trigger_edge = pyqtSignal(str)
    sig_set_trigger_mode = pyqtSignal(str)
    sig_set_debounce = pyqtSignal(int)

    # ── 日志信号 ──────────────────────────────────────────
    log_debug = pyqtSignal(str)
    log_info = pyqtSignal(str)
    log_warning = pyqtSignal(str)
    log_error = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        # -- 环形缓冲区 --
        self._rb = NumpyRingBuffer(1_000_000)

        # -- Worker 配置 --
        self._sample_rate_hz = 1000.0    # 采样率 (Hz)
        self._time_window_s = 1.0        # 时间窗口 (秒)
        self._scroll_offset = 0          # 滚动偏移 (数据点)
        self._screen_w = 800             # 屏幕像素宽度
        self._running = False            # 运行状态
        self._paused = False             # 暂停状态
        self._fps = 30                   # 帧率

        # -- 共享变量（Worker 写，主线程只读） --
        self._envelope_vmin = np.array([], dtype=np.float64)
        self._envelope_vmax = np.array([], dtype=np.float64)
        self._envelope_write_offset = 0

        # -- 触发 --
        self._trigger_config = TriggerConfig()

        # -- 帧定时器 --
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._onFrameTick)

        # -- 内部信号路由（信号→本对象槽，跨线程自动投递）--
        self.sig_set_sample_rate.connect(self._setSampleRate)
        self.sig_set_time_window.connect(self._setTimeWindow)
        self.sig_set_scroll_offset.connect(self._setScrollOffset)
        self.sig_set_screen_w.connect(self._setScreenW)
        self.sig_set_running.connect(self._setRunning)
        self.sig_set_fps.connect(self._setFps)
        self.sig_set_paused.connect(self._setPaused)
        self.sig_set_upper_threshold.connect(self._setUpperThreshold)
        self.sig_set_lower_threshold.connect(self._setLowerThreshold)
        self.sig_set_trigger_enabled.connect(self._setTriggerEnabled)
        self.sig_set_trigger_edge.connect(self._setTriggerEdge)
        self.sig_set_trigger_mode.connect(self._setTriggerMode)
        self.sig_set_debounce.connect(self._setDebounce)

    # ════════════════════════════════════════════════════════
    # 配置槽函数（由主线程通过信号跨线程调用）
    # ════════════════════════════════════════════════════════

    @pyqtSlot(float)
    def _setSampleRate(self, hz: float) -> None:
        self._sample_rate_hz = max(hz, 1.0)

    @pyqtSlot(float)
    def _setTimeWindow(self, s: float) -> None:
        self._time_window_s = max(s, 0.001)

    @pyqtSlot(int)
    def _setScrollOffset(self, offset: int) -> None:
        self._scroll_offset = max(offset, 0)

    @pyqtSlot(int)
    def _setScreenW(self, w: int) -> None:
        self._screen_w = max(w, 1)

    @pyqtSlot(bool)
    def _setRunning(self, running: bool) -> None:
        if running:
            self._running = True
            self._timer.start(int(1000 / max(self._fps, 1)))
            self.log_info.emit("示波器: 启动")
        else:
            self._running = False
            self._timer.stop()
            self.log_info.emit("示波器: 停止")

    @pyqtSlot(int)
    def _setFps(self, fps: int) -> None:
        self._fps = max(fps, 1)
        if self._running and not self._paused:
            self._timer.setInterval(int(1000 / self._fps))

    @pyqtSlot(bool)
    def _setPaused(self, paused: bool) -> None:
        self._paused = paused
        if self._running:
            if paused:
                self._timer.stop()
            else:
                self._timer.start(int(1000 / max(self._fps, 1)))

    @pyqtSlot(float)
    def _setUpperThreshold(self, val: float) -> None:
        self._trigger_config.high_thresh = val

    @pyqtSlot(float)
    def _setLowerThreshold(self, val: float) -> None:
        self._trigger_config.low_thresh = val

    @pyqtSlot(bool)
    def _setTriggerEnabled(self, enabled: bool) -> None:
        self._trigger_config.enabled = enabled

    @pyqtSlot(str)
    def _setTriggerEdge(self, edge: str) -> None:
        if edge in ("rising", "falling", "both"):
            self._trigger_config.edge = edge

    @pyqtSlot(str)
    def _setTriggerMode(self, mode: str) -> None:
        if mode in ("auto", "normal"):
            self._trigger_config.mode = mode

    @pyqtSlot(int)
    def _setDebounce(self, samples: int) -> None:
        self._trigger_config.debounce_samples = max(samples, 0)

    # ════════════════════════════════════════════════════════
    # 数据入口
    # ════════════════════════════════════════════════════════

    @pyqtSlot(object, int, int)
    def writeData(self, data: np.ndarray,
                  gap_count: int, interval_us: int) -> None:
        """接收协议解析器的解析结果（跨线程槽）

        Args:
            data: float64 ndarray，含前部 NaN gap
            gap_count: 前 N 个点为危险区域
            interval_us: 采样间隔微秒（当前未使用，预留给时基换算）
        """
        if self._paused:
            return
        if len(data) == 0:
            return

        overwritten = self._rb.write_batch(data)
        if overwritten > 0:
            self.log_warning.emit(
                f"示波器: ⚠ 缓冲区覆盖 {overwritten} 点")

    # ════════════════════════════════════════════════════════
    # 帧计算
    # ════════════════════════════════════════════════════════

    @pyqtSlot()
    def _onFrameTick(self) -> None:
        """帧计算：读取 RingBuffer → 触发检测 → 包络计算"""
        if not self._running or self._paused:
            return

        # 1. 计算数据窗口大小（含拖拽缓冲 margin）
        visible_samples = max(int(self._sample_rate_hz * self._time_window_s), 1)
        window_samples = int(visible_samples * self.ENVELOPE_MARGIN)

        # 2. 从 RingBuffer 读取
        data, start_idx, actual = self._rb.read_frame(
            window_samples, self._scroll_offset)

        if actual == 0:
            return

        # 3. 触发检测与对齐（仅作用于可见窗口 = visible_samples）
        if self._trigger_config.enabled and actual >= visible_samples:
            visible_data = data[:visible_samples]
            trigger_idx = detect_trigger(visible_data, self._trigger_config)
            if trigger_idx >= 0:
                # 触发点对齐到可见窗口 25% 位置
                target = int(visible_samples * 0.25)
                self._scroll_offset = max(
                    0, start_idx + trigger_idx - target)
                # 对齐后重新读取
                data, start_idx, actual = self._rb.read_frame(
                    window_samples, self._scroll_offset)
                if actual == 0:
                    return
            elif self._trigger_config.mode == "normal":
                # Normal 模式未触发 → 不更新显示（保持上一帧）
                return
            # Auto 模式未触发 → 继续使用当前数据

        # 4. 包络计算
        cache_size = max(int(self._screen_w * self.ENVELOPE_MARGIN), 1)

        if actual <= cache_size:
            # 不需要降采样, vmin=vmax=原始数据
            self._envelope_vmin = data
            self._envelope_vmax = data
        else:
            # 降采样包络: 将 actual 个数据点映射到 cache_size 个列
            vmin = np.empty(cache_size, dtype=np.float64)
            vmax = np.empty(cache_size, dtype=np.float64)
            seg_edges = np.linspace(0, actual, cache_size + 1).astype(int)

            with np.errstate(invalid='ignore'):
                for i in range(cache_size):
                    seg = data[seg_edges[i]:seg_edges[i + 1]]
                    has_valid = np.any(~np.isnan(seg))
                    if has_valid:
                        vmin[i] = np.nanmin(seg)
                        vmax[i] = np.nanmax(seg)
                    else:
                        vmin[i] = np.nan
                        vmax[i] = np.nan

            self._envelope_vmin = vmin
            self._envelope_vmax = vmax

        self._envelope_write_offset = start_idx

    # ════════════════════════════════════════════════════════
    # 控制方法（主线程直接调用，跨线程用信号）
    # ════════════════════════════════════════════════════════

    def set_buffer_size(self, size: int) -> None:
        """调整缓冲区容量（会清空现有数据）"""
        self._rb = NumpyRingBuffer(max(size, 100))

    def start(self) -> None:
        """启动帧计算"""
        self._running = True
        self._timer.start(int(1000 / max(self._fps, 1)))

    def stop(self) -> None:
        """停止帧计算"""
        self._running = False
        self._timer.stop()

    def clear(self) -> None:
        """清空缓冲区和包络缓存"""
        self._rb.clear()
        self._envelope_vmin = np.array([], dtype=np.float64)
        self._envelope_vmax = np.array([], dtype=np.float64)
        self._envelope_write_offset = 0

    # ── 阈值缓存更新（主线程调用，推送权威值用于绘制） ──

    def set_threshold_values(self, upper: float, lower: float) -> None:
        """由主线程调用，推送 Worker 的权威阈值值到画板可读位置

        画板通过阈值信号交互后，Worker 端确认最终值，
        通过此方法写回共享位置供画板读取。
        """
        # 当前简单实现: 阈值存储在 self._trigger_config，
        # 画板直接读取 _trigger_config.high/low_thresh
        # （画板在主线程读取 _trigger_config 的 Python 字段是原子的）
        pass
