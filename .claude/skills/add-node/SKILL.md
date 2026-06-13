---
name: add-node
description: >
  Add new nodes to the SignalRouterGraph project. Trigger when the user says "添加节点", "创建节点", "新节点", "add node", "new node", or wants to extend the project's node library with custom functionality. Also use this when the user wants to modify existing nodes (add/modify/delete ports, change threading model, etc.).
  This skill covers the full workflow: analyzing the user's requirements, determining whether the node needs multi-threading, choosing the right implementation pattern (simple file vs subdirectory with _Worker), creating the content widget UI (either code-based or .ui-based), registering the node, implementing serialization, and verifying it works.
  IMPORTANT: Before writing any code, always read the reference node implementations listed below to match the project's coding style and patterns.
---

# SignalRouterGraph — 添加新节点

## 概述

此 skill 指导你为信号路由图编辑器添加新节点。项目有两种节点模式：

| 模式 | 适用场景 | 参考实现 |
|---|---|---|
| **简单节点（单文件）** | 无 I/O、无线程，纯 UI 或 timer 驱动 | `test_node.py`、`data_sender_node.py`、`data_receiver.py` |
| **多线程节点（子目录）** | 有持续 I/O（串口、TCP、采样），需工作线程 | `serialport/`（最佳参考）、`oscilloscope/`、`network/` |

## 步骤

### Step 1：分析需求 — 先和用户确认以下问题

在动手前，必须和用户确认清楚。用自然语言对话，而不是让用户填空。

- **节点做什么？** — 数据从哪里来、到哪里去？纯处理还是有外部 I/O？
- **需要什么端口？** — 输入（槽）几个？输出（信号）几个？分别什么数据类型？
- **需要线程吗？** — 是否有阻塞/轮询/持续 I/O？是否需要在后台一直跑？
- **UI 上需要什么控件？** — 按钮、下拉框、输入框、显示控件？
- **需要保存/恢复什么状态？** — 哪些 UI 控件的值需要序列化？
- **数据流是怎样的？** — 信号触发频率？是否需要渲染握手（如示波器）？

### Step 2：确定实现模式

根据 Step 1 的答案选择模式：

#### 简单节点（单文件）

当 **所有条件** 都满足时选此模式：
- 没有阻塞 I/O（串口、TCP 等）
- 无工作线程
- UI 交互简单（或仅 timer 驱动）
- 不需要持续的 background 处理

**文件结构：** `connnodes/my_node.py`（一个文件包含 Content + Node）

**参考文件：**
- `connnodes/test_node.py` — 最简单的信号/槽示例
- `connnodes/data_sender_node.py` — timer 驱动 + 多端口示例

#### 多线程节点（子目录）

当 **任一条件** 满足时选此模式：
- 有外部 I/O（串口读写、TCP 通信、硬件采样）
- 需要在后台持续处理数据
- 有阻塞操作不能放在主线程
- 需要渲染握手（工作线程→主线程→工作线程）

**文件结构：**
```
connnodes/my_device/
├── __init__.py          # 节点类 + @register_node()
├── my_device_widget.py  # Content widget + _Worker 类
└── my_device_core.py    # 核心 I/O 逻辑（在工作线程中运行）
```

**参考文件：**
- `connnodes/serialport/` — ⭐ 最佳参考，模式最清晰
- `connnodes/oscilloscope/` — 渲染握手示例（frameReady → renderComplete）

### Step 3：创建内容部件（Content Widget）

#### 方式 A：纯代码布局（推荐）

直接用 PyQt5 布局代码搭建 UI。参考 `oscilloscope_widget.py` 或 `data_sender_node.py`。

```python
# connnodes/my_node.py
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox
from conn_base import ConnNodeContentWidget


class MyNodeContent(ConnNodeContentWidget):
    def initUI(self):
        layout = QVBoxLayout(self)
        
        # 控件行 1
        row1 = QHBoxLayout()
        self.combo = QComboBox()
        row1.addWidget(QLabel("选项:"))
        row1.addWidget(self.combo)
        layout.addLayout(row1)
        
        # 控件行 2
        self.btn = QPushButton("执行")
        layout.addWidget(self.btn)
        
        # 暗色主题样式
        self.setStyleSheet("""
            QComboBox {
                background-color: #202020;
                color: #e0e0e0;
            }
            QPushButton {
                background-color: #202020;
                color: #e0e0e0;
                border: 1px solid #404040;
                padding: 4px 8px;
            }
        """)
        
        self.resize(250, 150)  # 给节点一个合理的默认尺寸
    
    def cleanup(self):
        """清理资源。简单节点可为空，多线程节点必须清理线程"""
        ...
```

#### 方式 B：.ui 文件（适合复杂布局）

用 Qt Designer 设计 UI，保存到 `connnodes/my_device/my_device.ui`，然后运行 `ui_to_pyqt5.bat` 编译生成 `my_device_ui.py`。

然后在 widget 中使用：
```python
from .my_device_ui import Ui_MyDevice

class MyDeviceContent(ConnNodeContentWidget):
    def initUI(self):
        self.ui = Ui_MyDevice()
        self.ui.setupUi(self)
        # ... 后续初始化
```

参考 `connnodes/serialport/serialport_widget.py` + `serialport.ui`。

### Step 4：定义节点类

#### 简单节点模板

```python
from PyQt5.QtCore import pyqtSignal, QByteArray
from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf


@register_node()
class MyNode(ConnNode):
    tppath = ("分类", "节点名")     # ⚠️ 唯一标识，不可与已有节点重复
    icon = "icons/receiver.png"      # 面板图标
    name = "节点名"                  # 面板显示名称
    tooltip = "功能描述"             # 面板悬停提示
    conn_title = "节点标题"          # 节点上方显示的标题

    NodeContent_class = MyNodeContent

    def __init__(self, scene):
        super().__init__(scene,
            signalsConf=[            # 输出端口
                ConnSocketConf(
                    socketType=2,
                    key="output",
                    tooltip="输出说明",
                    name="输出",
                    argsType=(str,),  # 支持的类型: str, QByteArray, float
                ),
            ],
            slotsConf=[              # 输入端口
                ConnSocketConf(
                    socketType=1,
                    key="input",
                    tooltip="输入说明",
                    name="输入",
                    argsType=(str,),
                ),
            ]
        )
        # 注册信号和槽 —— key 必须与上面的 key 一致
        self.registerSignal("output", self.content.output_signal)
        self.registerSlot("input", self.content.some_slot_method)

    def initSettings(self):
        super().initSettings()
        self.input_multi_edged = True   # 允许输入连接多条边
        self.input_socket_position = LEFT_CENTER   # 端口位置
        self.output_socket_position = RIGHT_CENTER

    def serialize(self):
        res = super().serialize()
        # 保存 UI 状态：控件的值
        res["my_value"] = self.content.some_spin.value()
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        # 恢复 UI 状态
        self.content.some_spin.setValue(data.get("my_value", 0))
        return res
```

#### 多线程节点模板

```python
# connnodes/my_device/__init__.py

from .my_device_widget import MyDeviceContent
from conn_conf import register_node, set_node_display
from conn_base import ConnNode, ConnSocketConf
from PyQt5.QtCore import QByteArray


# 可选：注册分类的显示元数据
set_node_display(
    tppath=("分类",),
    tooltip="分类说明",
    icon="icons/sub.png",
)


@register_node()
class MyDeviceNode(ConnNode):
    tppath = ("分类", "节点名")
    icon = "icons/er.png"
    name = "节点名"
    tooltip = "功能描述"
    conn_title = "节点标题"

    NodeContent_class = MyDeviceContent

    def __init__(self, scene):
        super().__init__(scene,
            slotsConf=[
                ConnSocketConf(
                    socketType=1,
                    key="sendData",
                    tooltip="输入说明",
                    name="输入",
                    argsType=(QByteArray,),
                ),
            ],
            signalsConf=[
                ConnSocketConf(
                    socketType=2,
                    key="received",
                    tooltip="输出说明",
                    name="输出",
                    argsType=(QByteArray,),
                ),
            ]
        )
        # 注册工作线程对象的信号和槽引用（实际连接类型由全局配置决定）
        self.registerSignal("received", self.content.core.received)
        self.registerSlot("sendData", self.content.core.sendData)

    def initSettings(self):
        super().initSettings()
        self.input_multi_edged = True
        self.input_socket_position = LEFT_BOTTOM
        self.output_socket_position = RIGHT_BOTTOM

    def serialize(self):
        res = super().serialize()
        # 保存配置到 JSON
        res["config_value"] = self.content.config_value
        return res

    def deserialize(self, data, hashmap={}, restore_id=True):
        res = super().deserialize(data, hashmap, restore_id)
        # 恢复配置
        self.content.config_value = data.get("config_value", default)
        return res
```

### Step 5：实现 _Worker + QThread 模式（多线程节点）

在 widget 文件中实现。必须严格遵循以下模式：

```python
# connnodes/my_device/my_device_widget.py
from PyQt5.QtCore import QObject, pyqtSlot, QMetaObject, QThread, Qt
from PyQt5.QtWidgets import QVBoxLayout, QPushButton
from conn_base import ConnNodeContentWidget
from conn_utils import ThreadManager
from .my_device_core import MyDeviceCore


class MyDeviceContent(ConnNodeContentWidget):
    class _Worker(QObject):
        """工作线程辅助对象 — 在工作线程中创建核心 I/O 对象"""
        def __init__(self, parent=None):
            super().__init__(parent)
            self._is_init = False
            self.core: MyDeviceCore = None

        @pyqtSlot()
        def initCore(self):
            """此方法在工作线程中执行，创建核心对象"""
            if not self._is_init:
                self._is_init = True
                self.core = MyDeviceCore(self)

    def initUI(self):
        # ── 1. 创建线程并启动 ──
        self._worker = self.__class__._Worker()
        self._thread = QThread()
        self._thread.start()
        ThreadManager.instance().register_thread(self._thread)  # ⚠️ 必须注册

        # ── 2. 将 worker 移动到工作线程，然后阻塞式初始化 ──
        self._worker.moveToThread(self._thread)
        QMetaObject.invokeMethod(
            self._worker, "initCore", Qt.BlockingQueuedConnection
        )
        self.core: MyDeviceCore = self._worker.core  # 获取工作线程中的核心对象引用

        # ── 3. 搭建 UI（主线程） ──
        layout = QVBoxLayout(self)
        self.btn = QPushButton("控制")
        layout.addWidget(self.btn)
        self.resize(250, 150)

        # ── 4. 连接跨线程信号 ──
        # 注意：信号-槽连接在对象初始化完成后进行，
        # 使用 AutoConnection（默认），Qt 自动处理跨线程投递
        # 注：此处是节点内部信号连接，图边连接由全局配置控制
        self.core.ready.connect(self._onReady)
        self.btn.clicked.connect(self._onBtnClicked)

    def _onReady(self, data):
        """主线程槽 — 收到工作线程的数据"""
        # 更新 UI（主线程安全）
        pass

    def _onBtnClicked(self):
        """主线程槽 — UI 操作通过信号桥接到工作线程"""
        # 可以直接调用 core 的方法（内部信号会自动跨线程）
        self.core.doSomething()

    def cleanup(self):
        """⚠️ 必须清理线程！"""
        self.core.stop()  # 停止核心 I/O
        self._worker.deleteLater()
        self._thread.quit()
        self._thread.wait(3000)
        self._thread.deleteLater()
```

#### 核心 I/O 类模板

```python
# connnodes/my_device/my_device_core.py
from PyQt5.QtCore import QObject, pyqtSignal, QByteArray


class MyDeviceCore(QObject):
    """在工作线程中运行的核心 I/O 逻辑"""
    ready = pyqtSignal(QByteArray)  # 向主线程发送数据
    received = pyqtSignal(QByteArray)  # 节点输出端口信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # QSerialPort、QTcpSocket 等 I/O 对象在此创建
        # 此时已在工作线程中

    def sendData(self, data: QByteArray):
        """槽函数 — 从主线程接收数据并处理"""
        # 处理数据...
        pass

    def stop(self):
        """停止 I/O"""
        pass
```

### Step 6：端口类型与位置

#### 支持的数据类型

| 类型 | 用途 | 参考 |
|---|---|---|
| `QByteArray` | 二进制数据/协议包 | 发送器、TCP、串口、示波器、信号发生器 |
| `str` | 文本字符串 | TCP 文本发送 |
| `float` | 数值数据 | 可选扩展 |

#### 端口位置枚举

`socketType` 决定输入（1）或输出（2）。位置常量从 `nodeeditor.node_socket` 导入：

```python
from nodeeditor.node_socket import (
    LEFT_CENTER, RIGHT_CENTER,    # 左右居中（默认）
    LEFT_TOP, LEFT_BOTTOM,        # 左侧上/下
    RIGHT_TOP, RIGHT_BOTTOM,      # 右侧上/下
)
```

在 `initSettings()` 中设置：
```python
self.input_socket_position = LEFT_CENTER
self.output_socket_position = RIGHT_CENTER
```

### Step 7：编写协议解码（如需要）

如果节点需要解析波形采样协议，参考 `connnodes/waveform_protocol.py`：

```python
# connnodes/waveform_protocol.py 中已有波形协议定义：
# 帧头 (0xAA 0x55) + 采样间隔 (uint32) + 数据数 (uint16) + float32数组 + 校验 (XOR)
```

对于自定义协议，参考此文件中的编码/解码实现。

### Step 8：验证节点正常工作

创建完节点后，进行以下验证：

1. **节点出现在节点树面板** — 启动应用，检查节点树和右键菜单
2. **拖放创建节点** — 从节点树拖放到场景，或右键创建
3. **端口连接正常** — 拖拽连线，类型不匹配时应被拒绝并在日志中显示错误
4. **信号触发正确** — 连接后数据能正常流动到目标节点
5. **保存/加载** — 保存为 `.json` 后重新加载，节点状态（UI 控件值、连接）应完全恢复
6. **清理无泄漏** — 删除节点或关闭窗口时，不应有报错

### 约束提醒 ⚠️

1. **`tppath` 必须唯一** — 不能与 `CONN_NODES` 中已有节点重名
2. **新增端口必须追加到末尾** — 反序列化依赖声明顺序匹配，不在中间插入
3. **修改 `tppath` 会破坏旧文件** — 旧 json 无法反序列化此节点
4. **多线程节点必须注册线程** — 调用 `ThreadManager.instance().register_thread()`
5. **必须实现 `cleanup()`** — 多线程节点必须在此方法中停止线程
6. **跨线程初始化必须在 `initUI()` 中完成** — 反序列化时先初始化再连接
7. 端口 key 在 `signalsConf` / `slotsConf` 和 `registerSignal` / `registerSlot` 中**必须一致**
