# PWM 控制器节点 (PWMControllerNode) 设计文档

## 一、概述

PWM 控制器节点是信号路由图编辑器中的控制类节点，通过外接串口节点与 MCU 通信，实现 4 路 PWM 通道的频率、占空比、启用/禁用的实时控制。

**核心特性：**
- 固定 4 路本地通道，通过**起始通道偏移 (base channel)** 映射到不同的 MCU 通道段
- 每通道独立输入/输出端口：支持手动调节和自动控制两种模式
- 二进制协议通信：协议包通过串口发送到 MCU，MCU 响应经串口返回
- 定时刷新：周期性自动查询 MCU 内所有通道状态并更新 UI
- 暗色主题 UI：与项目整体风格一致

---

## 二、架构

### 2.1 整体架构

```
┌────────────────────────────────────────────────────────────┐
│                    主线程 (GUI)                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ PwmControllerWidget                                 │   │
│  │  ├── 操作栏: [获取PWM信息] [✓定时刷新] [间隔 ms]    │   │
│  │  ├── 起始通道: [QSpinBox 0~252]                    │   │
│  │  ├── 通道1 GroupBox (频率/占空比/启用)              │   │
│  │  ├── 通道2 GroupBox (频率/占空比/启用)              │   │
│  │  ├── 通道3 GroupBox (频率/占空比/启用)              │   │
│  │  ├── 通道4 GroupBox (频率/占空比/启用)              │   │
│  │  └── 状态标签                                       │   │
│  └────────────────┬────────────────────────────────────┘   │
│                   │ ▲ 信号/槽 (跨线程 AutoConnection)       │
│                   │ │                                      │
│                   ▼ │                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ _Worker (QObject, 在工作线程中)                      │   │
│  │  └── _PwmCore                                       │   │
│  │       ├── 协议包构造 (build_* 函数)                  │   │
│  │       ├── 响应解析 (decode_frame → 命令码分发)       │   │
│  │       └── Fetch 超时管理 (QTimer, 2s 超时)           │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────┘
           │                                     ▲
           │ 输出 QByteArray (协议包)            │ 输入 QByteArray (MCU 响应)
           ▼                                     │
┌────────────────────────────────────────────────────────────┐
│                       串口节点                              │
│  (SerialPortNode / TcpClient / 其他数据通道节点)            │
└────────────────────────────────────────────────────────────┘
```

### 2.2 线程模型

采用标准的 `_Worker + QThread` 模式：

1. `initUI()` 中创建 `_Worker` 对象和 `QThread`
2. 启动线程，用 `BlockingQueuedConnection` 调用 `initCore()` 在工作线程创建 `_PwmCore`
3. 所有后续通信通过 PyQt5 信号-槽跨线程投递（`AutoConnection`，Qt 自动识别跨线程→异步投递）

```
initUI():                         工作线程
   _Worker = _Worker()             (尚未开始)
   _thread = QThread()
   _thread.start()
   _worker.moveToThread(_thread)
   QMetaObject.invokeMethod(        ──▶  initCore()
     _worker, "initCore",               _core = _PwmCore(self)
     BlockingQueuedConnection)     ◀──  返回
   self._core = self._worker._core
   _connectSignals()
     _core.commandForChannel ───▶  AutoConnection → _onCommandForChannel
     _core.commandBroadcast  ───▶  AutoConnection → _onCommandBroadcast
     _core.pwmInfoReady      ───▶  AutoConnection → _onInfoReceived
     _core.setAckReady       ───▶  AutoConnection → _onAckReceived
     _core.errorReceived     ───▶  AutoConnection → _onErrorReceived
```

### 2.3 cleanup 销毁顺序

```python
def cleanup(self):
    self._autoFetchTimer.stop()       # 1. 停止定时器
    self._core.shutdown()             # 2. 关闭 Core (BlockingQueuedConnection)
    self._worker.deleteLater()        # 3. 销毁 Worker
    self._thread.quit()               # 4. 退出线程
    self._thread.wait(3000)           # 5. 等待线程结束 (3s 超时)
    self._thread.deleteLater()        # 6. 销毁线程
```

---

## 三、端口设计

### 3.1 端口列表

共计 **9 个端口**：4 输出 + 5 输入。

| 方向 | key | 类型 | 显示名 | 说明 |
|------|-----|------|--------|------|
| 输出 | `ch1_send` | QByteArray | CH1发送 | 通道1 协议包（MCU 通道 base+1） |
| 输出 | `ch2_send` | QByteArray | CH2发送 | 通道2 协议包（MCU 通道 base+2） |
| 输出 | `ch3_send` | QByteArray | CH3发送 | 通道3 协议包（MCU 通道 base+3） |
| 输出 | `ch4_send` | QByteArray | CH4发送 | 通道4 协议包（MCU 通道 base+4） |
| 输入 | `ch1_ctrl` | dict | CH1控制 | 通道1 dict 自动控制指令 |
| 输入 | `ch2_ctrl` | dict | CH2控制 | 通道2 dict 自动控制指令 |
| 输入 | `ch3_ctrl` | dict | CH3控制 | 通道3 dict 自动控制指令 |
| 输入 | `ch4_ctrl` | dict | CH4控制 | 通道4 dict 自动控制指令 |
| 输入 | `received` | QByteArray | 接收 | 共享 MCU 响应输入（所有通道共用） |

### 3.2 端口位置

```
输入 (左侧, LEFT_CENTER):  ch1_ctrl │            │ ch1_send :输出 (右侧, RIGHT_CENTER)
                           ch2_ctrl │   PWM 控制器 │ ch2_send
                           ch3_ctrl │              │ ch3_send
                           ch4_ctrl │              │ ch4_send
                           received  │            │
```

### 3.3 Dict 控制指令格式

每个 `chN_ctrl` 端口专用于对应通道，dict 中不需要 `channel` 字段：

```python
# 设置频率 (Hz)
{"freq": 1000}

# 设置占空比 (0.0-100.0%)
{"duty": 75.5}

# 启停
{"enable": True}
{"enable": False}

# 组合
{"freq": 2000, "duty": 50.0, "enable": True}

# 触发 Fetch
{"cmd": "fetch"}
```

---

## 四、起始通道偏移 (Base Channel)

### 4.1 设计意图

每个 PWM 控制器节点固定管理 4 路本地通道。通过配置**起始通道 (base channel)**，可以将这 4 路映射到不同的 MCU 通道区间，实现**单 MCU 多节点分段控制**。

```
实例 A: base=0 → MCU 通道 0,1,2,3  (UI 显示 "通道 1"~"通道 4")
实例 B: base=4 → MCU 通道 4,5,6,7  (UI 显示 "通道 5"~"通道 8")
实例 C: base=8 → MCU 通道 8,9,10,11 (UI 显示 "通道 9"~"通道 12")
```

### 4.2 影响范围

| 层 | 影响 |
|----|------|
| UI 显示 | GroupBox 标题 = `通道 {base + local_idx + 1}` |
| UI → Core | 所有控件事件调用 `_localToMcu(local_idx)` → 传 MCU 通道索引给 Core |
| Core → UI | `_onCommandForChannel` 接收 MCU 通道索引 → `_mcuToLocal()` → 路由到本地端口 |
| 序列化 | 保存/恢复 `base_channel` 值 |

### 4.3 关键方法

```python
def _localToMcu(self, local_idx: int) -> int:
    """本地通道索引 → MCU 通道索引"""
    return self._baseChannel + local_idx

def _mcuToLocal(self, mcu_ch_idx: int) -> int:
    """MCU 通道索引 → 本地通道索引（0-3），不在范围内返回 -1"""
    local = mcu_ch_idx - self._baseChannel
    return local if 0 <= local < self.CHANNEL_COUNT else -1
```

---

## 五、信号路由

### 5.1 Core 信号拆分

`_PwmCore` 将原来的单一 `commandReady(QByteArray)` 拆分为两个信号：

| 信号 | 参数 | 用途 |
|------|------|------|
| `commandForChannel` | `(int, QByteArray)` | 通道专用命令（SET_FREQ/SET_DUTY/SET_ENABLE）→ 路由到对应本地输出端口 |
| `commandBroadcast` | `(QByteArray)` | 广播命令（FETCH_PWM_INFO）→ 发送到所有 4 路输出端口 |

### 5.2 Widget 路由逻辑

```python
# Core → Widget 路由
self._core.commandForChannel.connect(self._onCommandForChannel)
self._core.commandBroadcast.connect(self._onCommandBroadcast)

def _onCommandForChannel(self, mcu_ch_idx, packet):
    """MCU 通道专用命令 → 路由到对应输出端口"""
    local = self._mcuToLocal(mcu_ch_idx)
    if local < 0:  # 不在本节点管理的范围内
        return
    [self.ch1Send, self.ch2Send, self.ch3Send, self.ch4Send][local].emit(packet)

def _onCommandBroadcast(self, packet):
    """广播命令 → 所有 4 路输出端口"""
    for sig in [self.ch1Send, self.ch2Send, self.ch3Send, self.ch4Send]:
        sig.emit(packet)
```

### 5.3 输出端口连接状态追踪

每路输出端口有独立的连接状态，用于控制 UI 控件的启用/禁用：

```python
def setChOutputConnected(self, local_idx: int, connected: bool):
    """由 Node.onEdgeConnectionChanged 调用"""
    self._ch_output_connected[local_idx] = connected
    self._applyChannelEnableState(local_idx)

def _applyChannelEnableState(self, local_idx):
    """最终启用状态 = 有 fetch 数据 AND 有输出连接 AND MCU 允许调节"""
    ch_info = self._last_channel_states[local_idx]
    has_output = self._ch_output_connected[local_idx]
    
    if ch_info is None:
        # 未 fetch → 全部禁用
        return
    
    freq_spin.setEnabled(has_output and ch_info.occupied and ch_info.freq_adjustable)
    duty_slider.setEnabled(has_output and ch_info.occupied and ch_info.duty_adjustable)
    enable_check.setEnabled(has_output and ch_info.occupied)
```

全局 fetch 按钮在没有任何输出端口连接时禁用。

---

## 六、通信协议

### 6.1 帧格式

二进制协议，详见 [`pwm_protocol.md`](pwm_protocol.md)：

```
[SOF 2B: 0xAA55][CMD 1B][PAYLOAD_LEN 2B LE][PAYLOAD N bytes][XOR CHECKSUM 1B]
```

### 6.2 命令码

| 方向 | 命令 | 码值 | 说明 |
|------|------|------|------|
| PC→MCU | CMD_FETCH_PWM_INFO | 0x10 | 查询所有 PWM 通道状态 |
| PC→MCU | CMD_SET_PWM_FREQ | 0x11 | 设置某路频率 |
| PC→MCU | CMD_SET_PWM_DUTY | 0x12 | 设置某路占空比 |
| PC→MCU | CMD_SET_PWM_ENABLE | 0x13 | 启用/禁用某路 |
| MCU→PC | CMD_PWM_INFO_REPORT | 0x20 | FETCH 响应，包含 4 路状态 |
| MCU→PC | CMD_PWM_SET_ACK | 0x21 | SET 命令确认 |
| MCU→PC | CMD_PWM_ERROR | 0xFF | 错误响应 |

### 6.3 Fetch 响应处理

MCU 的 `CMD_PWM_INFO_REPORT` 固定返回 `channel_count=4` 条通道记录，每条包含：

```
[name_len 1B][name N bytes UTF-8][flags 1B][freq_min 4B][freq_max 4B]
[freq_default 4B][freq_current 4B][duty_min 2B][duty_max 2B]
[duty_default 2B][duty_current 2B]
```

**flags 标志位：**
| 位 | 掩码 | 含义 |
|----|------|------|
| bit0 | 0x01 | FREQ_ADJUSTABLE — 频率可调 |
| bit1 | 0x02 | DUTY_ADJUSTABLE — 占空比可调 |
| bit2 | 0x04 | OCCUPIED — 通道被占用 |
| bit3 | 0x08 | ENABLED — 通道当前启用 |

Widget 收到后按 `index` 对应到本地通道，更新 UI 控件的范围和值，并根据 `occupied`/`adjustable` 标志决定控件启用状态。

---

## 七、UI 布局

### 7.1 布局结构

```
┌─────────────────────────────────────────┐
│ [获取PWM信息] [✓定时刷新] [1000ms]      │  ← 操作栏
│ 起始通道: [0] → 通道 1~4               │  ← 起始通道偏移
│─────────────────────────────────────────│  ← 分隔线
│ ┌ 通道 1 [占用] ─────────────────────┐  │
│ │ 频率: [1000 Hz]  占空比: [══50%━] [50.00%] │
│ │ [✓] 启用                           │  │
│ └────────────────────────────────────┘  │
│ ┌ 通道 2 [空闲] ─────────────────────┐  │
│ │ 频率: [0 Hz]    占空比: [────────] [0.00%] │
│ │ [ ] 启用                           │  │
│ └────────────────────────────────────┘  │
│ ┌ 通道 3 [占用] ─────────────────────┐  │
│ ┌ 通道 4 [占用] ─────────────────────┐  │
│                                        │
│ 就绪 — 点击「获取PWM信息」查询 MCU     │  ← 状态标签
└─────────────────────────────────────────┘
```

### 7.2 控件说明

| 区域 | 控件 | 范围 | 说明 |
|------|------|------|------|
| 操作栏 | 获取PWM信息按钮 | — | 手动触发 Fetch |
| 操作栏 | 定时刷新复选框 | — | 开启周期性自动 Fetch |
| 操作栏 | 间隔 SpinBox | 100-10000ms | 自动 Fetch 间隔 |
| 起始通道 | Base SpinBox | 0-252, step=4 | MCU 起始通道索引 |
| 每通道 | 频率 SpinBox | 0-999999 Hz | 目标频率 |
| 每通道 | 占空比 Slider | 0-10000 | 占空比滑块 |
| 每通道 | 占空比 DoubleSpinBox | 0.00-100.00% | 占空比精确值 |
| 每通道 | 启用 CheckBox | — | 通道启用/禁用 |
| 底部 | 状态标签 | — | 操作提示和错误信息 |

### 7.3 暗色主题样式

采用 `_applyStyleSheet()` 模式，整体暗色配色：

| 元素 | 颜色 |
|------|------|
| 背景 | `#0a0a0a` |
| GroupBox 边框 | `#404040` |
| 输入框背景 | `#202020` |
| 文字 | `#e0e0e0` |
| 滑块激活色 | `#5aadff` |
| 滑块已填充 | `#2a6a9a` |
| 按钮悬停边框 | `#5aadff` |
| 复选框选中 | `#2a6a9a` 背景 + `#5aadff` 边框 |

---

## 八、控制方式

### 8.1 手动控制

用户通过 UI 控件调节 → 立即通过 Core 发送 SET 命令：

```
用户调节频率 SpinBox
  → _onChannelFreqChanged(local_idx, freq_hz)
    → _core.setFreq(_localToMcu(local_idx), freq_hz)
      → commandForChannel.emit(mcu_ch_idx, packet)
        → _onCommandForChannel(mcu_ch_idx, packet)
          → chXSend.emit(packet)  (路由到对应输出端口)
```

### 8.2 自动控制

外部节点通过 `chN_ctrl` 端口发送 dict 指令：

```
信号发生器/脚本 发送 {"freq": 2000}
  → handleChNCtrl(dict) 
    → _handleChannelCtrl(local_idx, cmd)
      → _core.setFreq(_localToMcu(local_idx), 2000)
        → （同上，协议包路由到对应输出端口）
```

自动控制**不更新 UI 控件**，仅下发命令。UI 通过定时 fetch 或手动 fetch 同步 MCU 真实状态。

### 8.3 定时刷新

勾选「定时刷新」后，`QTimer` 以固定间隔调用 `_core.fetchPwmInfo()`，MCU 返回的 `CMD_PWM_INFO_REPORT` 更新所有通道 UI 控件的值和启用状态。

---

## 九、数据流（完整路径）

### 9.1 SET 命令（设置频率/占空比/启用）

```
用户调节 UI 控件
  │
  ▼
Widget 事件处理 (主线程)
  │ _localToMcu(local_idx) → mcu_ch_idx
  │ _core.setFreq(mcu_ch_idx, freq_hz)  (跨线程 AutoConnection)
  ▼
_PwmCore.setFreq() (工作线程)
  │ proto.build_set_freq(mcu_ch_idx, freq_hz) → QByteArray
  │ commandForChannel.emit(mcu_ch_idx, packet)  (跨线程 AutoConnection)
  ▼
Widget._onCommandForChannel() (主线程)
  │ _mcuToLocal(mcu_ch_idx) → local_idx
  │ [ch1Send..ch4Send][local_idx].emit(packet)
  ▼
串口节点发送数据 → MCU
  │
  ▼
MCU 返回 CMD_PWM_SET_ACK
  │
  ▼
串口节点 → PWM.received (QByteArray)
  │
  ▼
_PwmCore.handleResponse() (工作线程)
  │ decode_frame(data) → (CMD_PWM_SET_ACK, payload)
  │ decode_set_ack(payload) → {ch_idx, cmd, value}
  │ setAckReady.emit(ch_idx, cmd, value)
  │ (跨线程 AutoConnection)
  ▼
Widget._onAckReceived() (主线程)
  │ 日志记录确认信息
```

### 9.2 FETCH 查询（获取全部通道状态）

```
用户点击「获取PWM信息」
  │
  ▼
Widget._onFetchClicked() (主线程)
  │ _core.fetchPwmInfo()  (跨线程 AutoConnection)
  ▼
_PwmCore.fetchPwmInfo() (工作线程)
  │ proto.build_fetch_info() → QByteArray
  │ commandBroadcast.emit(packet)  (跨线程 AutoConnection)
  │ _fetch_timeout_timer.start(2000)
  ▼
Widget._onCommandBroadcast() (主线程)
  │ [ch1Send..ch4Send].forEach(sig => sig.emit(packet))
  ▼
串口节点发送数据 → MCU
  │
  ▼
MCU 返回 CMD_PWM_INFO_REPORT (4 条通道记录)
  │
  ▼
_PwmCore.handleResponse() (工作线程)
  │ decode_frame(data) → (CMD_PWM_INFO_REPORT, payload)
  │ decode_info_report(payload) → list[PwmChannelInfo]
  │ _fetch_timeout_timer.stop()
  │ pwmInfoReady.emit(channels)  (跨线程 AutoConnection)
  ▼
Widget._onInfoReceived() (主线程)
  │ 对每条记录:
  │   _applyChannelState(idx, ch)
  │     → 更新 SpinBox/Slider/CheckBox 值和范围
  │     → 更新 GroupBox 标题 (含 [占用]/[空闲] 状态)
  │     → 根据 occupied/adjustable 设置启用状态
  │   _applyChannelEnableState(idx)
  │     → 综合 fetch 数据 + 输出连接状态决定最终启用
```

---

## 十、序列化

### 10.1 保存字段

```python
{
    "pwm_channels": [
        {  # PwmChannelInfo.to_dict()
            "index": 0,
            "name": "1",
            "occupied": True,
            "freq_adjustable": True,
            "duty_adjustable": True,
            "enabled": True,
            "freq_min": 0,
            "freq_max": 999999,
            "freq_default": 0,
            "freq_current": 1000,
            "duty_min": 0,
            "duty_max": 10000,
            "duty_default": 0,
            "duty_current": 5000,  # 50.00%
        },
        # ... 通道 2~4
    ],
    "auto_refresh": True,
    "refresh_interval": 1000,
    "base_channel": 0,
}
```

### 10.2 恢复顺序

```python
def deserialize(self, data, hashmap={}, restore_id=True):
    # 1. 先恢复 base_channel（影响所有 UI 标题）
    self.content._baseSpin.setValue(data.get("base_channel", 0))
    
    # 2. 恢复通道 UI 值（不发送命令）
    channels_data = data.get("pwm_channels", [])
    if channels_data:
        self.content.restoreFromSerializedData(channels_data)
    
    # 3. 恢复定时刷新设置
    self.content._intervalSpin.setValue(data.get("refresh_interval", 1000))
    
    # 注: auto_refresh 仅读取标记，不自动开启
    # 原因：刚反序列化时可能尚未连接输出端口，自动开启可能导致无输出
    auto_refresh = data.get("auto_refresh", False)
    if auto_refresh:
        self.content._autoRefreshCheck.setChecked(False)  # 延迟到用户手动开启
```

---

## 十一、典型使用场景

### 11.1 PWM 控制器 → 串口 → MCU

```
[PWM控制器] ──(QByteArray)──▶ [串口] ──(UART)──▶ [MCU]
                              ▲
                              │
                              └──(UART)── [MCU 响应]
```

最典型的使用方式：PWM 控制器的 4 路输出连接到串口节点的发送端口，串口节点的接收端口连接回 PWM 控制器的「接收」端口。

**连线示例：**
- `PWM.CH1发送` → `串口.sendData`
- `PWM.CH2发送` → `串口.sendData` (可共用同一个串口发送端口)
- `PWM.CH3发送` → `串口.sendData`
- `PWM.CH4发送` → `串口.sendData`
- `串口.received` → `PWM.接收`

> **注意：** 串口为单通道，4 路输出可并联到同一串口发送端口，PWM 协议包中的 `channel_idx` 字段区分不同通道。

### 11.2 多节点分段控制

```
MCU 有 8 路 PWM 通道 (0-7):

[PWM控制器A (base=0)] ───▶ [串口] ──▶ [MCU 通道 0-3]
[PWM控制器B (base=4)] ───▶ [串口] ──▶ [MCU 通道 4-7]
```

两个 PWM 控制器节点共用同一串口节点（或不同串口），各自控制不同的 MCU 通道段。

### 11.3 自动控制脚本

```
[脚本节点/信号发生器] ──(dict {freq: 500})──▶ [PWM控制器.CH1控制]
```

通过 `ch1_ctrl` 端口发送 dict 指令，实现自动化控制。

---

## 十二、通道启用状态逻辑

UI 控件的启用/禁用由三个因素共同决定：

```
控件启用 = 有输出连接 AND 有 fetch 数据 AND MCU 允许调节
```

| 输出已连接 | 已 fetch | occupied | adjustable | 控件状态 |
|-----------|---------|----------|------------|---------|
| ❌ | — | — | — | 全部禁用 |
| ✅ | ❌ | — | — | 全部禁用（无数据） |
| ✅ | ✅ | ❌ | — | 全部禁用（通道未占用） |
| ✅ | ✅ | ✅ | ❌ | 仅启用/禁用复选框可用 |
| ✅ | ✅ | ✅ | ✅ | 完全可用 |

---

## 十三、错误处理

| 场景 | 行为 |
|------|------|
| FETCH 超时 (2s) | 状态标签显示"超时 — 请检查串口连接"，颜色变红 |
| 无效帧（校验失败） | `easyWarning` 日志记录，丢弃该帧 |
| MCU 返回错误码 | 状态标签显示错误描述（如"无效通道索引"） |
| 输出端口全断开 | Fetch 按钮禁用，定时刷新自动停止 |
| 非 dict 类型数据到达 ctrl 端口 | `easyWarning` 日志记录，忽略该消息 |

---

## 十四、修改指南

### 14.1 新增通道

1. 修改 `CHANNEL_COUNT` 从 4 改为目标值
2. 在 `__init__.py` 的 `signalsConf` 和 `slotsConf` 末尾追加端口声明
3. 在 `__init__.py` 末尾追加 `registerSignal`/`registerSlot` 调用
4. 在 `pwm_widget.py` 中追加对应的类属性信号 `chXSend`
5. 在 `_buildUI()` 的 `for i in range(CHANNEL_COUNT)` 循环自动处理 — 无需额外修改
6. 在 `_connectSignals()` 的 `for i in range(CHANNEL_COUNT)` 循环自动处理 — 无需额外修改

### 14.2 新增命令

1. 在 `pwm_protocol.py` 中定义新命令码和 `build_*` 函数
2. 在 `pwm_core.py` 中新增 `@pyqtSlot` 方法，调用 `commandForChannel.emit` 或 `commandBroadcast.emit`
3. 在 `handleResponse` 中添加新 MCU 命令码的 `elif` 分支
4. 在 `pwm_widget.py` 的 `_handleChannelCtrl` 中处理新的 dict 指令
5. 在 UI 中添加对应的控件

### 14.3 修改端口顺序

> **约束：** 端口顺序影响反序列化！新增端口必须追加到末尾，不得在中间插入。

---

## 十五、性能考量

| 关注点 | 说明 |
|--------|------|
| 线程隔离 | Core 在工作线程中运行，不阻塞 UI |
| 跨线程通信 | 所有信号使用 `AutoConnection`，Qt 自动异步投递 |
| 协议包 | 小体积二进制包（典型 6-12 字节），无序列化开销 |
| Fetch 间隔 | 默认 1000ms，可配 100-10000ms，避免频繁查询 MCU |
| 超时保护 | 2s 无响应触发超时处理，避免无限等待 |
| UI 更新 | 仅 fetch 响应时批量更新，手动调节时不更新 UI 控件 |
