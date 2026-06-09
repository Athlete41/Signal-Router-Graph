# 波形采样协议 (Waveform Protocol)

信号发生器↔示波器之间的二进制数据传输协议。数据以 `QByteArray` 形式在 ConnEdge 上传输。

---

## 协议格式

### 布局

| 偏移 | 大小 | 类型 | 字段 | 说明 |
|------|------|------|------|------|
| 0 | 2B | `0xAA 0x55` | 帧头 | 同步标识 |
| 2 | 4B | uint32 LE | 采样间隔 | 微秒(μs)，相邻数据点之间的时间间隔 |
| 6 | 2B | uint16 LE | 数据数 | 本包携带的 float32 数量 |
| 8 | N×4B | float32 LE | 数据载荷 | 波形数据点，小端序 IEEE 754 |
| 8+N×4B | 1B | uint8 | XOR 校验 | 从帧头到最后一个数据字节的 XOR |

### 最小包长度

帧头(2) + 采样间隔(4) + 数据数(2) + 0个数据(0) + 校验(1) = **9 字节**

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

## 编码 (发送端)

```python
from connnodes.waveform_protocol import encode_packet

# 采样间隔 1000μs（1ms），10 个数据点
qba = encode_packet(
    sampling_interval_us=1000,
    data=[0.0, 0.5878, 0.9511, 0.9511, 0.5878,
          0.0, -0.5878, -0.9511, -0.9511, -0.5878],
)
# 返回 QByteArray，可直接通过 ConnEdge 发送
```

### 字节序列示例

以下为 `encode_packet(1000, [1.0, 2.0, 3.0])` 的完整 19 字节输出：

```
AA 55          ← 帧头
E8 03 00 00    ← 采样间隔 1000μs (uint32 LE)
03 00          ← 数据数 3 (uint16 LE)
00 00 80 3F    ← 1.0 (float32 LE)
00 00 00 40    ← 2.0 (float32 LE)
00 00 40 40    ← 3.0 (float32 LE)
0B             ← XOR 校验 (= AA^55^E8^03^00^00^03^00^00^00^80^3F^00^00^00^40^00^00^40^40)
```

---

## 解码 (接收端)

```python
from connnodes.waveform_protocol import decode_packet

result = decode_packet(qba)
if result is not None:
    sampling_interval_us = result["sampling_interval_us"]  # int
    data = result["data"]  # list[float]
```

### 解码校验

`decode_packet()` 按顺序做以下检查，任一不通过返回 `None`：

1. **长度检查**：`ba.size() < 9` → 拒绝
2. **帧头检查**：`raw[0] != 0xAA` 或 `raw[1] != 0x55` → 拒绝
3. **校验检查**：XOR 不匹配 → 拒绝
4. **长度验证**：`len(raw) != MIN_PACKET_SIZE + data_count * 4` → 拒绝

---

## 数据流完整路径

```
信号发生器 / TCP / 串口等数据源
  │
  │ data = [生成波形数据点]  # list[float]
  │ qba = encode_packet(sampling_interval_us, data)
  │ emit dataOutput(qba)  →  pyqtSignal(QByteArray)
  ▼
ConnEdge (跨线程/同线程 AutoConnection)
  │
  ▼
示波器 OscilloscopeSampler.writeData(qba)
  │ result = decode_packet(qba)
  │ if result: ring_buffer.write_batch(result["data"])
  ▼
RingBuffer (存储原始数据，不在此处应用 amp/offset)
  │
  ▼ (帧定时器 tick)
_emitFrame()
  │ buf.read_frame(visible_count, scroll_offset)
  │ data = [v * amp + offset for v in data]  # 统一应用
  │ emit frameReady(data, ...)
  ▼
主线程渲染
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
