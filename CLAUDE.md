# 信号路由图编辑器 (SignalRouterGraph)

基于 PyQt5 + nodeeditor 框架的可视化节点编辑器。节点间的连接**不是 eval 驱动的计算调用**，而是**基于 PyQt5 信号-槽机制**的实时数据流连接，支持多线程。

---

## 一、环境与启动

- Python 3.10.11
- 依赖：`nodeeditor==0.9.15`、`PyQt5==5.15.9`、`pyqt5_sip==12.18.0`、`QtPy==2.4.3`

```bash
pip install -r requirements.txt
python main.py
```

UI 文件修改后需重新编译：
```bash
ui_to_pyqt5.bat   # 递归查找 .ui 文件并调用 pyuic5 生成 _ui.py
```

---

## 二、架构总览

### 六层架构

| 层 | 位置 | 职责 | 修改影响 |
|---|---|---|---|
| **第1层** — nodeeditor 框架 | `site-packages/nodeeditor/` | 场景图管理、QGraphicsItem 渲染、序列化/反序列化骨架、撤销/重做 | 不直接改，继承后重写 |
| **第2层** — 自定义核心基类 | `conn_base.py` | ConnNode/ConnEdge/ConnScene/ConnSocket 等基类 | 🚨 影响所有节点和边 |
| **第3层** — 应用窗口 | `conn_window.py` / `conn_sub_window.py` | MDI 主窗口、标签页、拖放、右键菜单、文件 I/O | ⚠️ 窗口布局或文件操作时涉及 |
| **第4层** — 面板组件 | `conn_tool_panel.py` / `conn_nodes_panel.py` / `conn_global_setting_panel.py` / `conn_thread_panel.py` | 侧边面板容器、节点树（拖放创建）、全局设置、线程计数显示 | 低 |
| **第5层** — 用户自定义节点 | `connnodes/` | 所有业务节点，通过 `@register_node()` 注册 | ✅ 增删改节点不涉及其他层 |
| **第6层** — 工具类 | `conn_utils.py` | SimpleLogger（单例 UI 日志器）、ThreadManager（单例线程管理器） | ⚠️ 日志和线程管理 |

### 文件分布

```
Signal-Router-Graph/
├── main.py                      # 程序入口
├── conn_base.py                 # 核心基类（第2层）
├── conn_conf.py                 # 注册中心 + 全局设置（第2层）
├── conn_window.py               # MDI 主窗口（第3层）
├── conn_sub_window.py           # 标签页 / 拖放 / 右键菜单（第3层）
├── conn_tool_panel.py           # 工具面板容器（第4层）
├── conn_nodes_panel.py          # 节点树面板（第4层）
├── conn_global_setting_panel.py # 全局设置面板（第4层）
├── conn_thread_panel.py         # 线程计数面板（第4层）
├── conn_utils.py                # 工具类 - 日志+线程管理（第6层）
├── connnodes/                   # 用户自定义节点（第5层）
│   ├── __init__.py              # 自动发现子模块
│   └── ...                      # 节点扩展目录，按需添加
├── qss/                         # 样式表
├── icons/                       # 图标
├── note/                        # 🤚 用户个人笔记（Claude 不可修改）
└── test.json / error.json       # 示例图文件
```

### 数据流

```
方向：信号驱动，非 eval 驱动
路径：源节点 pyqtSignal → ConnEdge.connect() → 目标节点槽函数
跨线程：全局连接类型 (Auto/Queued) 控制跨线程投递方式
握手示例（示波器）：工作线程 emit frameReady → 主线程渲染 → emit renderComplete → 工作线程继续
```

### 注册中心启动顺序

```
conn_window.py → conn_sub_window.py → conn_base.py (line22: import GlobalSettingManager)
                                                    → conn_conf.py (line137: from connnodes import *)
                                                      → connnodes/__init__.py  发现子包
                                                        → 各子包 __init__.py  执行 @register_node()
```

**这意味着：** `conn_base.py` 在 `from connnodes import *` 之前已被部分加载。子包中的节点类不能反过来 `from conn_base import ConnNode`（会导致循环导入）。正确的做法是节点类定义在子包的 `__init__.py` 中，由 `conn_conf` 的 `from connnodes import *` 触发注册。

### 文件操作流程

```
保存: serialize() → Scene.serialize() → 各节点/边 serialize() → JSON
加载: deserialize() → Scene.deserialize() → 重建节点/边 → 恢复连接
```

---

## 三、核心类层次

### conn_base.py 类层次

```
Serializable + QGraphicsPathItem
  ├── ConnGraphicsEdge      — 带箭头的边绘制
  ├── ConnSceneClipboard    — 复制粘贴（修复框架硬编码 Edge 类的问题）
  ├── ConnEdge              — 信号 connect/disconnect/reconnect 管理
  ├── ConnScene             — 场景 + 边验证器注册 + reconnectAll()
  ├── ConnGraphicsNode      — 可拖拽调整大小的图形节点
  ├── ConnGraphicsSocket    — 带文本标签的端口绘制
  └── ConnSocketConf        — 端口配置数据类

QWidget + Serializable
  └── ConnNodeContentWidget — 内容部件基类（需重写 initUI/cleanup）

Node (from nodeeditor)
  └── ConnNode              — 自定义节点基类
        ├── _signals / _slots — 信号/槽注册字典
        ├── registerSignal()  — 注册 Qt 信号到输出端口
        ├── registerSlot()    — 注册可调用对象到输入端口
        ├── onEdgeConnectionChanged() — 边连接/断开时触发
        └── remove()          → 调用 content.cleanup()

Socket (from nodeeditor)
  └── ConnSocket            — 端口，带 argsType 类型验证

Edge (from nodeeditor)
  └── ConnEdge              — 信号连接管理
```

### conn_conf.py — 注册中心

```
CONN_NODES: dict[tuple[str], type]    # tppath → 节点类的映射
ALL_NODES_DISPLAY: dict               # tppath → 显示元数据

register_node(tppath=None)            # 装饰器，将节点类注册到 CONN_NODES
register_node_now(path, cls)          # 底层注册函数
set_node_display(tppath, ...)         # 设置面板分类的显示信息
get_class_from_tppath(tppath)         # 从 CONN_NODES 查找节点类

GlobalSettingManager                  # 全局配置单例
  ├── connectionType                  # 连接类型（Auto/Queued）
  └── viewUpdateMode                  # 视口更新模式
```

### conn_utils.py — 工具类

| 类/函数 | 用途 | 注意事项 |
|---|---|---|
| `SimpleLogger` | 单例 UI 日志器（彩色 HTML） | 线程安全 |
| `ThreadManager` | 线程生命周期管理 | 所有 QThread 必须注册 |
| `isRealSignal(obj)` | 判断是否 Qt 信号 | 检查 connect/disconnect/emit 方法 |
| `isQObjectInstanceMethod(slot)` | 判断是否 QObject 方法 | 用于 cross-thread 槽验证 |
| `disconnectAll(signal, slot)` | 安全断开所有同名连接 | 比 `disconnect` 更稳健 |

### 信号-槽连接生命周期

```
1. 用户拖拽连接两个端口
2. ConnScene 验证 argsType / 禁止循环连接
3. ConnEdge 创建，两端 socket 关联
4. onEdgeConnectionChanged() 触发
   ├── 获取 signal_owner.getSignal(key) → qt 信号
   ├── 获取 slot_owner.getSlot(key)    → 槽函数
   └── signal.connect(slot, connectionType)  ← 实际连接

5. 连接类型切换（全局设置）
   └── scene.reconnectAll(newType) → 每条 edge.signalReconnect()

6. 断开连接
   └── signalDisconnect() → signal.disconnect(slot)

7. 节点删除
   └── Node.remove() → content.cleanup() → 移除所有边
```

### 信号传递类型行为（实证结论）

**行为取决于信号声明的类型，而非连接方式。**

| 信号类型 | 传的值类型 | 行为 |
|----------|-----------|------|
| `pyqtSignal(list)` | list | 深拷贝 |
| `pyqtSignal(dict)` | dict | 引用传递 |
| `pyqtSignal(object)` | list | 引用传递 |
| `pyqtSignal(object)` | dict | 引用传递 |
| `pyqtSignal(object)` | numpy.ndarray | 引用传递 |

见 `note/test_cross_thread_array_结论.md`（实测数据）

### 线程模型

```
主线程（GUI）
  ├── QGraphicsView / QGraphicsScene 渲染
  ├── ConnNodeContentWidget 生命周期
  └── QThread 管理

工作线程（每个 I/O 节点一个）
  ├── 核心 I/O 对象（TcpClient / SerialPort / OscilloscopeSampler）
  ├── 通过 _Worker.init* 创建（BlockingQueuedConnection）
  └── 信号自动跨线程投递（节点内部信号用默认 AutoConnection，图边连接由全局配置决定）
```

#### 关键模式：_Worker + QThread

```python
class _Worker(QObject):
    @pyqtSlot()
    def initCore(self):
        self.core = CoreClass(self)  # 在工作线程创建

# initUI 中:
self._worker = _Worker()
self._thread = QThread()
self._thread.start()
ThreadManager.instance().register_thread(self._thread)
self._worker.moveToThread(self._thread)
QMetaObject.invokeMethod(self._worker, "initCore", Qt.BlockingQueuedConnection)
self.core = self._worker.core  # 获取引用
```

---

## 四、节点操作指南

### 4.1 添加新节点

#### 简单节点（单文件，无线程）

```python
# connnodes/my_node.py
from PyQt5.QtCore import pyqtSignal
from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf, ConnNodeContentWidget


class MyContent(ConnNodeContentWidget):
    """内容部件"""
    output_signal = pyqtSignal(str)  # 输出信号

    def initUI(self):
        self.resize(200, 120)
        # ... 搭建 UI 控件 ...

    def cleanup(self):
        ...  # 清理资源


@register_node()
class MyNode(ConnNode):
    tppath = ("分类名", "节点名")   # 唯一标识，不可重复
    icon = "icons/receiver.png"
    name = "节点名"                 # 面板显示名称
    tooltip = "提示文本"
    conn_title = "显示标题"          # 节点上方标题

    NodeContent_class = MyContent

    def __init__(self, scene):
        super().__init__(scene,
            signalsConf=[           # 输出端口
                ConnSocketConf(socketType=2, key="output_signal",
                    name="输出", tooltip="...", argsType=(str,)),
            ],
            slotsConf=[             # 输入端口
                ConnSocketConf(socketType=1, key="input_slot",
                    name="输入", tooltip="...", argsType=(str,)),
            ]
        )
        self.registerSignal("output_signal", self.content.output_signal)
        self.registerSlot("input_slot", self.content.some_method)

    def initSettings(self):
        super().initSettings()
        self.input_socket_position = LEFT_CENTER  # 端口位置

    def serialize(self): ...      # 保存状态
    def deserialize(self, ...): ... # 恢复状态
```

**关键步骤：**
1. 建文件 → 2. 定义 `NodeContent`（继承 `ConnNodeContentWidget`）→ 3. 定义节点类 + `@register_node()` → 4. `registerSignal`/`registerSlot` → 5. `cleanup()`

#### 多线程节点（子目录 + _Worker 模式）

见 `connnodes/oscilloscope/` 或 `connnodes/network/tcp_client_widget.py` 的完整实现。

```python
# 在内容部件中使用 _Worker + QThread 模式
class MyContent(ConnNodeContentWidget):
    class _Worker(QObject):
        def __init__(self):
            self.core: MyCore = None
        
        @pyqtSlot()
        def initCore(self):
            self.core = MyCore(self)  # 在工作线程创建核心对象

    def initUI(self):
        # 1. 创建线程
        self._worker = self.__class__._Worker()
        self._thread = QThread()
        self._thread.start()
        ThreadManager.instance().register_thread(self._thread)
        
        # 2. 移动 + 初始化
        self._worker.moveToThread(self._thread)
        QMetaObject.invokeMethod(self._worker, "initCore", Qt.BlockingQueuedConnection)
        self.core = self._worker.core  # 获取工作线程对象引用

    def cleanup(self):
        self._worker.deleteLater()
        self._thread.quit()
        self._thread.wait(3000)
        self._thread.deleteLater()
```

### 4.2 ConnSocketConf 参数速查

| 参数 | 值 | 说明 |
|---|---|---|
| `socketType` | `1` = 输入(槽) / `2` = 输出(信号) | 端口颜色和位置 |
| `key` | 字符串 | 与 `registerSignal/registerSlot` 的 key 对应 |
| `name` | 字符串 | 端口显示标签 |
| `tooltip` | 字符串 | 鼠标悬停提示（自动追加类型信息） |
| `argsType` | `(type,)` | 参数类型元组，如 `(str,)`、`(float,)`、`(QByteArray,)` |

**重要：** `argsType` 用于边连接时的类型验证，只有相同 `argsType` 的端口才能相连。

### 4.3 数据输入/输出类型参考

| 类型 | 用途 |
|---|---|
| `QByteArray` | 二进制数据 / 协议包 |
| `str` | 文本字符串 |
| `float` | 数值数据 |

### 4.4 修改节点的注意事项

| 操作 | 注意事项 |
|---|---|
| 新增端口 | **必须追加到 signalsConf/slotsConf 列表末尾**，不得在中间插入（反序列化依赖顺序） |
| 修改 `tppath` | 改变节点唯一标识，旧文件无法反序列化此节点 |
| 删除端口 | 反序列化旧文件会失败（端口数量不匹配） |
| 修改端口 key | registerSignal/registerSlot 的 key 必须同步修改 |

### 4.5 调试技巧

| 问题 | 排查方法 |
|---|---|
| 节点不出现 | 检查 `@register_node()` 是否添加，`tppath` 是否与已有节点冲突 |
| 端口连不上 | 检查两端的 `argsType` 是否完全一致 |
| 信号没触发 | 检查 `registerSignal` 的 key 是否与 `signalsConf` 匹配 |
| 跨线程问题 | 确保槽函数是 QObject 方法（框架约束，与连接类型无关） |
| 销毁时报错 | 检查 `cleanup()` 是否清理了线程和子对象 |

---

## 五、框架修改热点

### 修改热点速查

| 要改什么 | 改哪里 | 风险 |
|---|---|---|
| 端口样式 | `ConnGraphicsSocket.paint()` | 低 — 纯绘制改动 |
| 边样式/箭头 | `ConnGraphicsEdge.paint()` | 低 — 纯绘制改动 |
| 节点样式/标题 | `ConnGraphicsNode.paint()` | 低 — 纯绘制改动 |
| 端口类型验证规则 | `ConnScene.__init__()` 中的 `edge_type_validator` | ⚠️ 影响所有端口连接 |
| 信号连接逻辑 | `ConnEdge.signalConnect() / signalDisconnect()` | 🚨 影响所有数据流 |
| 序列化/反序列化 | `ConnEdge.deserialize()` / `ConnScene.deserialize()` | 🚨 影响文件 I/O |
| 节点初始化流程 | `ConnNode.__init__()` | 🚨 影响所有节点 |
| 复制粘贴逻辑 | `ConnSceneClipboard` | ⚠️ 影响复制粘贴 |
| 添加 socket 位置选项 | `ConnSocketConf` + `ConnNode` | 低 — 新增枚举值 |

### 常见修改场景

**场景 A：修改端口连接验证规则**
- 位置：`conn_base.py` 约第 289 行的 `edge_type_validator`
- 改动：修改验证函数的返回逻辑
- 影响：所有端口连接都会经过新验证

**场景 B：修改序列化格式**
- 位置：`ConnEdge.deserialize()` + `Scene.deserialize()`
- 注意事项：向前兼容旧文件格式

**场景 C：添加全局设置项**
- 位置：`conn_conf.py` 的 `GlobalSettingManager` + `conn_global_setting_panel.py`
- 用法：新增属性 + 信号 + UI 控件

**场景 D：修改线程管理策略**
- 位置：`conn_utils.py` 的 `ThreadManager`
- 注意事项：`shutdown_all_threads()` 在应用退出时调用

---

## 六、重要约束

1. **tppath 唯一**：两个节点不能有相同的 `tppath`，否则强制抛异常
2. **端口顺序敏感**：反序列化依靠声明顺序重连，新增端口必须追加到末尾
3. **禁止循环连接**：禁止 signal↔signal 和 slot↔slot
4. **必须 cleanup()**：节点销毁必须显式清理线程和子对象
5. **跨线程先初始化**：必须在 `initUI()` 中完成 QThread 创建和 moveToThread，再触发连接
6. **反序列化端口匹配**：端口靠**声明顺序**匹配（不是靠 key 或 name），新增端口必须追加在末尾
7. **线程注册**：所有 `QThread` 必须通过 `ThreadManager.instance().register_thread()` 注册，防止 GC 回收

---

## 七、任务执行流程

收到需求后按以下步骤执行：

1. **分析需求** — 拆解用户描述，明确要改什么、涉及哪些文件、影响范围
2. **追问边界** — 对于模糊的地方、没提到的边界情况、可选的实现方向，向用户提问确认
3. **等待确认** — 得到用户明确的答复后再开始动手
4. **执行并更新** — 逐步完成改动
5. **收尾** — 确认改动完成

---

## 九、禁止自作主张

1. **严禁在未获明确许可的情况下运行 `main.py`、执行测试脚本或以任何其他形式测试代码。** 即使你认为改动"显然正确"，也不得替用户做运行/测试的决定。
2. 只能改动任务明确涉及的文件。执行前确认改动范围，不得擅自修改框架代码（`conn_base.py`、`conn_conf.py` 等第1-2层文件）。

---

## 八、note/ 目录说明

`note/` 目录存放用户的个人笔记和设计文档。这些是用户自己写的内容，**Claude 不得修改、删除或重命名其中任何文件**。可以读取以了解项目背景，但不应做任何改动。

| 文件 | 说明 |
|---|---|
| `note/设计文档.md` | 项目整体设计文档 |
| `note/PyQt5.15.9信号特性.md` | PyQt5 信号机制研究笔记 |
| `note/nodeeditor0.9.15特性笔记.md` | nodeeditor 框架研究笔记 |
| `note/test_disconnect.py` | 信号 disconnect 行为测试脚本 |
| `note/test_emit.py` | 跨线程 emit 投递策略测试脚本 |
| `note/test_cross_thread_array_结论.md` | PyQt5 跨线程信号传递行为实证结论（list/dict/ndarray） |

> 节点相关设计文档随对应节点放在各自目录下，如 `connnodes/oscilloscope/示波器节点设计文档.md`
