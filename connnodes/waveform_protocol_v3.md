# 波形采样协议 V3 (Waveform Protocol v3)

信号发生器↔示波器之间的二进制数据传输协议。数据以 `QByteArray` 形式在 ConnEdge 上传输。

---

## 协议格式

### 布局

| 偏移 | 大小 | 类型 | 字段 | 说明 |
|------|------|------|------|------|
| 0 | 2B | `0xAA 0x55` | 帧头 | 同步标识 |
| 2 | 1B | uint8 | 通道 ID | 数据包所属通道（0-255），预留多通道扩展 |
| 3 | 4B | uint32 LE | 采样间隔 | 微秒(μs)，相邻数据点之间的时间间隔 |
| 7 | 2B | uint16 LE | 数据数 | **总浮点数数量**（含 gap 点 + 有效数据） |
| 9 | 4B | uint32 LE | 起始丢弃数 | 数据载荷前 N 个点为不可信丢弃点（危险区域） |
| 13 | N×4B | float32 LE | 数据载荷 | 前 `gap_count` 个为 `NaN` 魔法数字（标记危险区域），其后为有效波形数据 |
| 13+N×4B | 2B | uint16 LE | CRC-16 校验 | 从帧头到最后一个数据字节的 CRC-16/CCITT |

### 最小包长度

帧头(2) + 通道ID(1) + 采样间隔(4) + 数据数(2) + gap数(4) + 0个数据(0) + 校验(2) = **15 字节**

### 校验算法

CRC-16/CCITT（多项式 0x1021），采用 `binascii.crc_hqx` 标准实现。

校验范围：从帧头第一个字节到最后一个数据字节（不包括校验 2 字节本身）。

---

## 魔法数字

危险区域（gap）点的 float32 值为 `NaN`（IEEE 754 `0x7FC00000`），解码后可用 `math.isnan()` 检测。

接收端应：
1. 解码协议包，获取 `gap_count` 和数据列表
2. 前 `gap_count` 个值为 `NaN`，表示**不可信丢弃点**
3. 画板将这些点绘制为红色线段（与正常波形断开）

---

## 编码 (发送端)

```python
from connnodes.waveform_protocol_v3 import encode_packet

# 采样间隔 1000μs（1ms），10 个数据点，无 gap，通道 0
qba = encode_packet(
    sampling_interval_us=1000,
    data=[0.0, 0.5878, 0.9511, 0.9511, 0.5878,
          0.0, -0.5878, -0.9511, -0.9511, -0.5878],
)

# 带 3 个 gap 点的包（前 3 个点编码为 NaN）
qba = encode_packet(
    sampling_interval_us=1000,
    data=[0.0, 0.5878, 0.9511],
    gap_count=3,
)

# 指定通道 ID
qba = encode_packet(
    sampling_interval_us=500,
    data=[1.0, 2.0, 3.0],
    channel_id=1,
)
```

### 字节序列示例

`encode_packet(1000, [1.0, 2.0, 3.0], channel_id=0)` → **27 字节**：

```
AA 55          ← 帧头 [2B]
00             ← 通道 ID 0 (uint8) [1B]
E8 03 00 00    ← 采样间隔 1000μs (uint32 LE) [4B]
03 00          ← 数据数 3 (uint16 LE) [2B]
00 00 00 00    ← gap数 0 (uint32 LE) [4B]
00 00 80 3F    ← 1.0 (float32 LE) [4B]
00 00 00 40    ← 2.0 (float32 LE) [4B]
00 00 40 40    ← 3.0 (float32 LE) [4B]
## ##          ← CRC-16 校验 [2B]
```

---

## 解码 (接收端)

```python
from connnodes.waveform_protocol_v3 import decode_packet

result = decode_packet(qba)
if result is not None:
    sampling_interval_us = result["sampling_interval_us"]  # int
    data = result["data"]  # list[float] — 包含前部 NaN 魔法数字
    gap_count = result["gap_count"]  # int — 头部危险点数
    channel_id = result["channel_id"]  # int — 通道 ID
```

### 解码校验

`decode_packet()` 按顺序做以下检查，任一不通过返回 `None`：

1. **长度检查**：`ba.size() < 15` → 拒绝
2. **帧头检查**：`raw[0] != 0xAA` 或 `raw[1] != 0x55` → 拒绝
3. **校验检查**：CRC-16 不匹配 → 拒绝
4. **长度验证**：`ba.size() != 15 + 4 × data_count` → 拒绝

---

## 设计决策

| 决策 | 理由 |
|------|------|
| 二进制而非 JSON/文本 | 浮点数二进制传输无需解析开销，适合高频波形数据 |
| CRC-16/CCITT 而非 XOR | Python 标准库 `binascii.crc_hqx` C 实现，比 Python 级 XOR 循环快数倍；STM32 侧可用查表或硬件 CRC 加速；2B 开销对典型包（>100B）可忽略 |
| 小端序 | x86 原生小端，避免字节序转换 |
| float32 而非 float64 | 示波器显示精度 24bit 足够，带宽减半 |
| 帧头 `0xAA55` | 两字节非 ASCII 模式，降低与文本协议混淆的概率 |
| 采样间隔随包携带 | 支持动态变采样率，无需额外控制通道 |
| NaN 作为危险区域魔法数字 | IEEE 754 标准 sentinel，`math.isnan()` 检测极快，不可能与有效数据值冲突 |
| gap_count 在协议头中 | 解码时立即知道危险区长度，无需逐点扫描后才知道 |
| 通道 ID 1 字节 | 支持 256 个通道，足够未来多通道示波器扩展，仅 1B 开销 |
| 通道 ID 紧挨帧头（偏移 2） | 通道 ID 是路由标识，解码器先读通道 ID 再决定后续处理逻辑；紧挨帧头可在不解完全包的情况下提前分流 |
| gap_count 升 uint32 | uint16（65535）是硬边界——大缓冲区或高采样率长时间累积可能超出。uint32 仅增加 2B 开销 |
