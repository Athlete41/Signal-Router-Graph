# 波形采样协议 (Waveform Protocol)

信号发生器↔示波器之间的二进制数据传输协议。数据以 `QByteArray` 形式在 ConnEdge 上传输。

---

## 协议格式

### 布局

| 偏移 | 大小 | 类型 | 字段 | 说明 |
|------|------|------|------|------|
| 0 | 2B | `0xAA 0x55` | 帧头 | 同步标识 |
| 2 | 4B | uint32 LE | 采样间隔 | 微秒(μs)，相邻数据点之间的时间间隔 |
| 6 | 2B | uint16 LE | 数据数 | **总浮点数数量**（含 gap 点 + 有效数据） |
| 8 | 2B | uint16 LE | 起始丢弃数 | 数据载荷前 N 个点为不可信丢弃点（危险区域） |
| 10 | N×4B | float32 LE | 数据载荷 | 前 `gap_count` 个为 `NaN` 魔法数字（标记危险区域），其后为有效波形数据 |
| 10+N×4B | 1B | uint8 | XOR 校验 | 从帧头到最后一个数据字节的 XOR |

> **版本变更 v1→v2**：偏移 8 新增 `起始丢弃数` 字段（2B），数据载荷偏移从 8 变为 10。
> 向后兼容：新解码器仍可解析 v1 包（此时 gap_count=0），v1 编码器在新解码器中数据将被正确读取（gap_count=0）。

### 最小包长度

帧头(2) + 采样间隔(4) + 数据数(2) + gap数(2) + 0个数据(0) + 校验(1) = **11 字节**

### 校验算法

```python
def xor_checksum(data: bytes) -> int:
    ck = 0
    for b in data:
        ck ^= b
    return ck
```

校验范围：从帧头第一个字节到最后一个数据字节（不包括校验字节本身）。

---

## 魔法数字

危险区域（gap）点的 float32 值为 `NaN`（IEEE 754 `0x7FC00000`），解码后可用 `math.isnan()` 检测。

接收端应：
1. 解码协议包，获取 `gap_count` 和数据列表
2. 前 `gap_count` 个值为 `NaN`，表示**不可信丢弃点**
3. 画板将这些点绘制为红色线段（与绿色有效波形断开）

---

## 编码 (发送端)

```python
from connnodes.waveform_protocol import encode_packet

# 采样间隔 1000μs（1ms），10 个数据点，无 gap
qba = encode_packet(
    sampling_interval_us=1000,
    data=[0.0, 0.5878, 0.9511, 0.9511, 0.5878,
          0.0, -0.5878, -0.9511, -0.9511, -0.5878],
)

# 带 3 个 gap 点的包（前 3 个点编码为 NaN）
qba = encode_packet(
    sampling_interval_us=1000,
    data=[0.0, 0.5878, 0.9511],
    gap_count=3,  # 数据前插入 3 个 NaN 标记危险区域
)
```

### 字节序列示例

以下为 `encode_packet(1000, [1.0, 2.0, 3.0])` 的完整 **21** 字节输出（注意 v2 格式新增 2B gap 字段）：

```
AA 55          ← 帧头
E8 03 00 00    ← 采样间隔 1000μs (uint32 LE)
03 00          ← 数据数 3 (uint16 LE)
00 00          ← gap数 0 (uint16 LE)
00 00 80 3F    ← 1.0 (float32 LE)
00 00 00 40    ← 2.0 (float32 LE)
00 00 40 40    ← 3.0 (float32 LE)
##             ← XOR 校验
```

---

## 解码 (接收端)

```python
from connnodes.waveform_protocol import decode_packet

result = decode_packet(qba)
if result is not None:
    sampling_interval_us = result["sampling_interval_us"]  # int
    data = result["data"]  # list[float] — 包含前部 NaN 魔法数字
    gap_count = result["gap_count"]  # int — 头部危险点数
```

### 解码校验

`decode_packet()` 按顺序做以下检查，任一不通过返回 `None`：

1. **长度检查**：`ba.size() < 9` → 拒绝
2. **帧头检查**：`raw[0] != 0xAA` 或 `raw[1] != 0x55` → 拒绝
3. **校验检查**：XOR 不匹配 → 拒绝
4. **长度验证**：通过实际长度自动检测 v1（9+4N）或 v2（11+4N），均不匹配 → 拒绝

> **v1/v2 自动检测**：读取 `data_count` 后计算两种格式的期望长度，匹配 v1 则 `gap_count=0`，匹配 v2 则从偏移 8 读取 `gap_count`。v1 格式解码器向下兼容，旧版编码数据无需修改即可被新版解码器解析。

---

## 数据流完整路径

```
信号发生器 / TCP / 串口等数据源
  │
  │ data = [生成波形数据点]  # list[float]
  │ qba = encode_packet(sampling_interval_us, data, gap_count=0)
  │ emit dataOutput(qba)  →  pyqtSignal(QByteArray)
  ▼
ConnEdge (跨线程/同线程 AutoConnection)
  │
  ▼
示波器 OscilloscopeSampler.writeData(qba)
  │ result = decode_packet(qba)
  │ if result: ring_buffer.write_batch(result["data"])

  ▼ (Temp 缓存溢出 → gap_count > 0)
  │ _flushBuffer():
  │   data = [NaN] * gap_count + real_data  # 插入魔法数字
  │   emit frameReady(data_with_nan, gap_count, interval_us)
  ▼

主线程 OscilloscopeContent._onFrameReady()
  │ strip NaN markers → clean_data → history_rb.write_batch(clean_data)
  │ _render_frame() reads from history_rb
  │   if pending_gap > 0: data = [nan] * gap + data  # 重新插入 NaN
  │   waveform.setData(data_with_nan, ...)
  ▼

WaveformWidget.paintEvent()
  │ math.isnan(val) → red segment (detached from green)
  │ not NaN → green waveform
  ▼
屏幕渲染

```

---

## 扩展示例

### TCP 透传波形数据

```python
# 服务端收到外部设备的二进制数据后直接转发
# 只要数据符合协议格式，示波器即可解析
tcp_socket.readyRead.connect(lambda: (
    oscilloscope.writeData(tcp_socket.readAll())
))
```

### 串口转发

```python
# 串口收到的数据以 QByteArray 直接转发
serial.readyRead.connect(lambda: (
    oscilloscope.writeData(serial.readAll())
))
```

---

## 设计决策

| 决策 | 理由 |
|------|------|
| 二进制而非 JSON/文本 | 浮点数二进制传输无需解析开销，适合高频波形数据 |
| XOR 而非 CRC | 包短（通常 < 1KB），XOR 足够检测单 bit 翻转且计算极快 |
| 小端序 | x86 原生小端，避免字节序转换 |
| float32 而非 float64 | 示波器显示精度 24bit 足够，带宽减半 |
| 帧头 `0xAA55` | 两字节非 ASCII 模式，降低与文本协议混淆的概率 |
| 采样间隔随包携带 | 支持动态变采样率，无需额外控制通道 |
| NaN 作为危险区域魔法数字 | IEEE 754 标准 sentinel，`math.isnan()` 检测极快，不可能与有效数据值冲突 |
| gap_count 在协议头中 | 解码时立即知道危险区长度，无需逐点扫描后才知道 |
