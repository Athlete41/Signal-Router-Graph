# PWM 控制器通信协议

## 概述

上位机（PC）通过串口与下位机（MCU）通信，控制多路 PWM 输出。

- 物理层：UART 串口
- 帧同步：帧头 `0xAA 0x55`
- 校验：XOR（帧头到载荷末尾）
- 字节序：小端 (Little Endian)

---

## 帧格式

```
字节偏移 | 字段       | 大小 | 类型       | 说明
---------|------------|------|------------|--------------------------
0        | SOF        | 2    | uint8[2]   | 帧头，固定 0xAA 0x55
2        | CMD        | 1    | uint8      | 命令码
3        | PAYLOAD_LEN| 2    | uint16 LE  | 载荷字节数（可为 0）
5        | PAYLOAD    | N    | bytes      | 载荷数据
5+N      | CHECKSUM   | 1    | uint8      | XOR 校验
```

**最小帧长度：6 字节**（SOF + CMD + LEN(0) + CHECKSUM）

**校验范围：** 字节 0 到 4+N（即 SOF 到 PAYLOAD 最后一个字节），不含校验字节自身。

---

## 命令码

### PC → MCU

| 命令 | 码值 | 说明 |
|------|------|------|
| CMD_FETCH_PWM_INFO | 0x10 | 查询所有 PWM 通道状态（无载荷） |
| CMD_SET_PWM_FREQ   | 0x11 | 设置某路频率 |
| CMD_SET_PWM_DUTY   | 0x12 | 设置某路占空比 |
| CMD_SET_PWM_ENABLE | 0x13 | 启用/禁用某路 |

### MCU → PC

| 命令 | 码值 | 说明 |
|------|------|------|
| CMD_PWM_INFO_REPORT | 0x20 | FETCH_PWM_INFO 的响应 |
| CMD_PWM_SET_ACK     | 0x21 | SET 命令的确认 |
| CMD_PWM_ERROR       | 0xFF | 错误响应 |

---

## 载荷结构

### CMD_FETCH_PWM_INFO（PC → MCU）

无载荷（PAYLOAD_LEN = 0）。

### CMD_SET_PWM_FREQ（PC → MCU）

共 6 字节：

```
[channel_idx 2B uint16 LE] [freq_hz 4B uint32 LE]
```

- `channel_idx`: MCU 通道索引（uint16 LE），取值取决于上位机设置的起始通道偏移
- `freq_hz`: 目标频率，单位 Hz

### CMD_SET_PWM_DUTY（PC → MCU）

共 4 字节：

```
[channel_idx 2B uint16 LE] [duty 2B uint16 LE]
```

- `channel_idx`: MCU 通道索引
- `duty`: 占空比，0-10000 对应 0.00%-100.00%（0.01% 精度）

### CMD_SET_PWM_ENABLE（PC → MCU）

共 3 字节：

```
[channel_idx 2B uint16 LE] [enable 1B uint8]
```

- `channel_idx`: MCU 通道索引
- `enable`: 0 = 禁用，1 = 启用

### CMD_PWM_INFO_REPORT（MCU → PC）

```
[channel_count 1B uint8] [通道1记录] [通道2记录] [通道3记录] [通道4记录]
```

`channel_count` 固定为 4。

每条通道记录结构（25 + name_len 字节）：

```
[name_len 1B uint8]
[name N bytes UTF-8]         # 通道名称，如 "1", "2", "3", "4"
[flags 1B uint8]              # 标志位
[freq_min 4B uint32 LE]       # 频率最小值 (Hz)
[freq_max 4B uint32 LE]       # 频率最大值 (Hz)
[freq_default 4B uint32 LE]   # 频率默认值 (Hz)
[freq_current 4B uint32 LE]   # 频率当前值 (Hz)
[duty_min 2B uint16 LE]       # 占空比最小值 (0-10000)
[duty_max 2B uint16 LE]       # 占空比最大值 (0-10000)
[duty_default 2B uint16 LE]   # 占空比默认值 (0-10000)
[duty_current 2B uint16 LE]   # 占空比当前值 (0-10000)
```

**flags 标志位定义：**

| 位 | 掩码 | 含义 |
|----|------|------|
| bit0 | 0x01 | FREQ_ADJUSTABLE — 频率是否可调 |
| bit1 | 0x02 | DUTY_ADJUSTABLE — 占空比是否可调 |
| bit2 | 0x04 | OCCUPIED — 通道是否被占用（有外设使用中） |
| bit3 | 0x08 | ENABLED — 通道当前是否启用 |

### CMD_PWM_SET_ACK（MCU → PC）

```
[channel_idx 2B uint16 LE] [cmd_echo 1B uint8] [value 变长]
```

`value` 长度取决于 `cmd_echo`：

| cmd_echo | value 长度 | 类型 |
|----------|-----------|------|
| 0x11 (SET_PWM_FREQ) | 4 字节 | uint32 LE |
| 0x12 (SET_PWM_DUTY) | 2 字节 | uint16 LE |
| 0x13 (SET_PWM_ENABLE) | 1 字节 | uint8 |

### CMD_PWM_ERROR（MCU → PC）

```
[error_code 1B uint8] [channel_idx 2B uint16 LE]
```

`channel_idx` 为 `0xFFFF` 表示不是特定通道的错误。

**错误码定义：**

| 码值 | 含义 |
|------|------|
| 0x01 | 无效命令 |
| 0x02 | 无效通道索引 |
| 0x03 | 数值超出范围 |
| 0x04 | 通道参数不可调 |
| 0x05 | 校验错误 |
| 0x06 | 通道未被占用 |

---

## 交互流程示例

### 查询通道状态

```
PC:  [0xAA 0x55] [0x10] [0x00 0x00] [0xEF]
     SOF          CMD    LEN=0       XOR

MCU: [0xAA 0x55] [0x20] [0x1C 0x00] [通道1~4记录] [校验]
```

### 设置通道 1 频率为 1000 Hz

```
PC:  [0xAA 0x55] [0x11] [0x06 0x00] [0x00 0x00] [0xE8 0x03 0x00 0x00] [校验]
     SOF          CMD    LEN=6       ch_idx=0    freq=1000

MCU: [0xAA 0x55] [0x21] [0x07 0x00] [0x00 0x00] [0x11] [0xE8 0x03 0x00 0x00] [校验]
     SOF          CMD    LEN=7       ch_idx=0    cmd=0x11 freq=1000
```

### 设置通道 3 占空比为 75%

```
PC:  [0xAA 0x55] [0x12] [0x04 0x00] [0x02 0x00] [0x4C 0x1D] [校验]
     SOF          CMD    LEN=4       ch_idx=2    duty=7500(=75.00%)

MCU: [0xAA 0x55] [0x21] [0x05 0x00] [0x02 0x00] [0x12] [0x4C 0x1D] [校验]
```

---

## 上位机行为说明

1. **起始通道偏移** 每个 PWM 控制器节点可配置 base channel（默认 0），4 路本地通道映射到 MCU 通道 `base`~`base+3`。所有 `channel_idx` 字段发送/接收均为 MCU 真实通道索引，协议包本身不感知 base。
2. **Fetch 按钮** 发送 `CMD_FETCH_PWM_INFO`，协议包分发到所有 4 路输出端口。等待 `CMD_PWM_INFO_REPORT` 响应更新 UI。
3. **定时刷新** 勾选后周期性自动发送 `CMD_FETCH_PWM_INFO`（默认 1000ms）。
4. **手动调节** 用户修改 UI 控件时通过对应输出端口立即发送 `CMD_SET_*`，协议包中的 `channel_idx` = base + 本地通道索引。
5. **自动控制** 通过 per-channel dict 输入端口（`ch1_ctrl`~`ch4_ctrl`）接收 `{"freq": ..., "duty": ..., "enable": ...}` 指令，解析后下发 `CMD_SET_*`，不更新 UI 控件。UI 仅通过 fetch 同步。

## MCU 端实现建议

1. 上电后初始化 4 路 PWM 通道，设置默认频率和占空比。
2. 收到 `CMD_FETCH_PWM_INFO` 时返回当前 4 路通道的真实状态。
3. 收到 `CMD_SET_*` 时校验通道索引和参数范围，成功返回 `CMD_PWM_SET_ACK`，失败返回 `CMD_PWM_ERROR`。
4. 未占用的通道其 freq_adjustable/duty_adjustable 应为 0。
5. 帧间应有足够的间隔（建议 ≥ 2ms）以便上位机正确分帧。
