# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

信号路由图编辑器 — 基于 PyQt5 + nodeeditor 框架的可视化节点编辑器。与传统节点编辑器的区别在于：节点间的连接**不是 eval 驱动的计算调用**，而是**基于 PyQt5 信号-槽机制**的实时数据流连接，支持多线程。

## 环境与启动

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

## 项目架构

### 层次结构

**第1层 — nodeeditor 框架（外部依赖）**
- 提供场景图、节点渲染、边渲染、序列化、撤销/重做等基础设施
- 所有核心类通过继承进行自定义

**第2层 — 自定义核心基类（conn_base.py）**
- `ConnNode` — 自定义节点，带信号/槽注册系统和 PyQt5 信号端口模型
- `ConnEdge` — 自定义边，管理 PyQt5 信号-槽连接的 connect/disconnect/reconnect
- `ConnScene` — 自定义场景，支持重连逻辑
- `ConnSocket` — 端口，带工具提示、名称和参数类型信息
- `ConnGraphicsNode` — 可调整大小的图形节点
- `ConnGraphicsSocket` — 带文本标签的图形端口
- `ConnGraphicsEdge` — 带方向箭头的图形边
- `ConnSceneClipboard` — 复制/粘贴板，使用 ConnEdge 替代基类 Edge

**第3层 — 应用窗口（conn_window.py、conn_sub_window.py）**
- `ConnectionWindow` — MDI 主窗口，包含 Dock、菜单、工具栏
- `ConnSubWindow` — 单个图编辑器标签页，处理拖放创建、右键菜单、文件 I/O

**第4层 — 面板组件**
- `conn_tool_panel.py` — 侧边面板容器
- `conn_nodes_panel.py` — 节点树面板（拖放创建节点）
- `conn_global_setting_panel.py` — 全局设置（视口更新模式、连接类型）
- `conn_thread_panel.py` — 线程计数显示

**第5层 — 用户自定义节点（connnodes/）**
- 通过 `@register_node()` 装饰器注册
- 每个节点通过 `ConnSocketConf` 定义信号端口和槽端口

**第6层 — 工具类（conn_utils.py）**
- `SimpleLogger` — 单例 UI 日志器，带彩色 HTML 输出
- `ThreadManager` — 单例线程生命周期管理器，带 QTimer 自动清理

### 数据流

```
用户操作 --> 源节点发出 pyqtSignal
    --> ConnEdge 连接信号到槽（AutoConnection / QueuedConnection）
        --> 目标节点槽函数接收数据 --> 更新 UI 或处理数据
```

### 关键设计决策

1. **信号驱动而非 eval 驱动**：不使用 `eval()` 计算输出，而是直接连接 Qt 信号到 Qt 槽，支持实时响应和多线程
2. **全局连接类型**：所有连接使用相同类型（AutoConnection 或 QueuedConnection），通过全局配置统一控制，避免每种连接单独管理
3. **序列化标识**：`tppath` 元组（如 `("数据源", "发送器")`）是节点的唯一标识，**不可重名**
4. **端口序数依赖**：反序列化时端口重连依赖于**端口声明顺序**，新增端口推荐追加到列表末尾，不要在中间插入

## 节点开发指南

### 创建新节点

在 `connnodes/` 目录下新建 `.py` 文件，按以下步骤：

1. 定义 `NodeContent` 类（继承 `ConnNodeContentWidget`），在其中定义 `pyqtSignal` 和槽函数
2. 定义节点类（继承 `ConnNode`），设置类属性（`tppath`、`icon`、`name`、`conn_title` 等）
3. 在 `__init__` 中调用 `super().__init__(scene, signalsConf=[...], slotsConf=[...])`
4. 在 `__init__` 中调用 `self.registerSignal(key, signal)` 和 `self.registerSlot(key, callable)`
5. 添加 `@register_node()` 装饰器
6. **必须**实现 `cleanup()` 方法进行显式清理

### ConnSocketConf 参数

| 参数 | 说明 |
|------|------|
| `socketType` | 2=信号(输出)、1=槽(输入) |
| `key` | 端口键（必填），与 registerSignal/registerSlot 的 key 对应 |
| `tooltip` | 提示文本 |
| `name` | 显示名称 |
| `argsType` | 参数类型元组，如 `(str,)`，用于连接时参数类型验证 |

## 重要约束

1. **节点路径不可重复**：两个节点不能拥有相同的 `tppath`，否则强制抛异常
2. **端口顺序敏感**：反序列化时依靠**声明顺序**重连端口。新增端口必须追加到末尾，不得在中间插入
3. **禁止循环连接**：不允许信号端口与信号端口连接，不允许槽端口与槽端口连接
4. **同信号可多次连接同一槽**：PyQt5 支持，但断开时按 LIFO 顺序逐一断开
5. **多线程注意事项**：必须在初始化阶段完成 QThread 创建和对象移动，再触发连接事件
6. **节点销毁**：必须重写 `cleanup()` 显式清理子对象和线程资源

## 核心模块速查

| 文件 | 职责 |
|------|------|
| `main.py` | 应用入口 |
| `conn_window.py` | MDI 主窗口 |
| `conn_sub_window.py` | 图编辑器标签页，拖放/菜单/文件操作 |
| `conn_base.py` | 所有核心基类（Node、Edge、Scene、Socket 等） |
| `conn_conf.py` | 节点注册中心、全局配置管理器、版本号 |
| `conn_utils.py` | 日志、线程管理、工具函数 |
| `conn_nodes_panel.py` | 节点树面板 |
| `conn_global_setting_panel.py` | 全局设置面板 |
| `conn_thread_panel.py` | 线程计数面板 |
| `conn_tool_panel.py` | 侧边面板容器 |
| `connnodes/__init__.py` | 自动发现并导入所有节点模块 |
| `qss/nodeeditor-dark.qss` | 暗色主题样式表 |

## 设计文档

详细的设计文档和决策记录位于 `note/` 目录下，包含：
- `note/设计文档.md` — 完整设计文档（中文）
- `note/PyQt5.15.9信号特性.md` — PyQt5 信号特性研究
- `note/nodeeditor0.9.15特性笔记.md` — nodeeditor 框架笔记
- `note/test_disconnect.py` / `note/test_emit.py` — 信号行为测试脚本
