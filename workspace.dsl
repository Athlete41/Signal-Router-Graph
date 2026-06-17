workspace "SignalRouterGraph" "基于 PyQt5 + nodeeditor 框架的可视化信号路由图编辑器。节点间通过 PyQt5 信号-槽机制实现实时数据流连接，支持多线程。" {

    model {
        // ═══════════════════════════════════════════════════════════════
        // 人员 (Actors)
        // ═══════════════════════════════════════════════════════════════
        user = person "工程/测试人员" "使用信号路由图编辑器创建信号处理流水线，配置数据源、协议解析和波形显示等节点" "User"

        // ═══════════════════════════════════════════════════════════════
        // 主系统
        // ═══════════════════════════════════════════════════════════════
        signalRouterGraph = softwareSystem "SignalRouterGraph" "信号路由图编辑器 — 可视化节点编辑器，基于 PyQt5 信号-槽机制实现实时数据流连接，支持多线程。" {

            // ── 桌面应用容器 ──────────────────────────────────────────
            desktopApp = container "桌面应用" "基于 PyQt5 的桌面 GUI 应用程序" "Python 3.10 / PyQt5" {

                // ── 应用窗口层 ────────────────────────────────────────
                mainWindow = component "ConnectionWindow (conn_window.py)" "MDI 主窗口 — 菜单栏、工具栏、DockWidget、状态栏、QSettings 持久化" "Python / QMainWindow" "UI"
                subWindow = component "ConnSubWindow (conn_sub_window.py)" "图编辑器标签页 — 拖放创建节点、右键菜单、视图滚轮跳转" "Python / NodeEditorWidget" "UI"

                // ── 面板系统 ─────────────────────────────────────────
                toolPanel = component "QDMToolPanel (conn_tool_panel.py)" "工具面板容器 — 承载节点树和其他工具面板" "Python / QWidget" "UI"
                nodeTree = component "节点树面板 (conn_nodes_panel.py)" "TreeBox 分类展示所有已注册节点，支持拖放创建" "Python / QTreeWidget" "UI"
                globalSettings = component "全局设置面板 (conn_global_setting_panel.py)" "视图更新模式 + 信号连接类型（Auto/Queued）切换" "Python / QWidget" "UI"
                loggerPanel = component "日志面板 (conn_simplelogger_panel.py)" "彩色 HTML 日志显示" "Python / QWidget" "UI"
                threadPanel = component "线程计数面板 (conn_thread_panel.py)" "实时显示当前活跃线程数" "Python / QWidget" "UI"

                // ── 场景图引擎 (conn_base.py) ─────────────────────────
                graphNode = component "ConnGraphicsNode" "可拖拽调整大小的节点 QGraphicsItem 渲染" "Python / QGraphicsItem" "Core"
                graphEdge = component "ConnGraphicsEdge" "带箭头的边绘制" "Python / QGraphicsPathItem" "Core"
                graphSocket = component "ConnGraphicsSocket" "带文本标签的端口绘制" "Python / QGraphicsItem" "Core"
                nodeBase = component "ConnNode" "节点基类 — 信号/槽注册字典、端口配置、序列化接口" "Python / Node" "Core"
                edgeBase = component "ConnEdge" "信号 connect/disconnect/reconnect 生命周期管理" "Python / Edge" "Core"
                sceneBase = component "ConnScene" "场景管理 + 边验证器注册 + reconnectAll()" "Python / QGraphicsScene" "Core"
                socketBase = component "ConnSocket" "端口，带 argsType 类型验证" "Python / Socket" "Core"
                contentBase = component "ConnNodeContentWidget" "内容部件基类 — initUI/cleanup 接口" "Python / QWidget" "Core"
                socketConf = component "ConnSocketConf" "端口配置数据类" "Python dataclass" "Core"
                clipboard = component "ConnSceneClipboard" "复制粘贴（修复框架硬编码 Edge 类）" "Python / Clipboard" "Core"

                // ── 节点注册中心 (conn_conf.py) ───────────────────────
                nodeRegistry = component "节点注册中心 (conn_conf.py)" "CONN_NODES 字典映射 + @register_node() 装饰器 + GlobalSettingManager 单例" "Python" "Core"

                // ── 工具层 (conn_utils.py) ─────────────────────────────
                utilsLayer = component "工具层 (conn_utils.py)" "SimpleLogger（单例 UI 日志器）+ ThreadManager（单例线程管理）+ 信号/槽工具函数" "Python" "Core"

                // ── 数据源类节点 ──────────────────────────────────────
                tcpClient = component "TCP客户端" "连接到远程服务器进行 TCP 数据收发（多线程）" "Python / QThread" "Node"
                tcpServer = component "TCP服务端" "TCP 服务端，接受多客户端连接并广播数据" "Python / QThread" "Node"
                serialPort = component "简单串口" "串口数据源，提供收发端口" "Python / QSerialPort" "Node"
                textSender = component "文本发送器" "文本编辑 + 文件加载 + 定时器发送" "Python / QTimer" "Node"
                hexSender = component "Hex发送器" "编辑 Hex 字符串并发送为 QByteArray" "Python" "Node"
                sineWaveGen = component "正弦波发生器 (gen_sine_wave.py)" "生成正弦波采样数据以 QByteArray 格式输出" "Python / numpy" "Node"

                // ── 可视化节点 ────────────────────────────────────────
                oscilloscope = component "示波器 V3" "4 通道波形显示，每通道独立 QThread + NumpyRingBuffer + 包络渲染（30 FPS QTimer 绘制）" "Python / QThread ×4 / numpy" "Node"
                hexReceiver = component "Hex接收器" "接收 QByteArray 并以 Hex 字符串形式显示" "Python" "Node"
                textReceiver = component "文本接收器" "接收 str 并追加到文本浏览器" "Python" "Node"

                // ── 数据处理节点 ──────────────────────────────────────
                parser1ch = component "协议解析器V3-1ch" "单通道协议解析，接受 QByteArray，输出 (ndarray, gap_count, interval_us)" "Python / QThread" "Node"
                parser2ch = component "协议解析器V3-2ch" "双通道协议解析，支持 channel_offset" "Python / QThread" "Node"
                parser4ch = component "协议解析器V3-4ch" "四通道协议解析，支持 channel_offset" "Python / QThread" "Node"

                // ── 控制节点 ──────────────────────────────────────────
                pwmController = component "PWM控制器" "4 路 PWM 通道控制，支持手动/自动 + 串口通信" "Python / QThread" "Node"

                // ── 协议工具 ──────────────────────────────────────────
                protocolUtils = component "波形协议 V3 编解码 (waveform_protocol_v3.py)" "V3 协议包的 encode/decode 实现（非节点，工具库）" "Python / numpy / struct" "Node"
            }

            // ── 外部框架依赖容器 ────────────────────────────────────
            nodeeditor = container "nodeeditor v0.9.15" "开源节点编辑框架 — 场景图管理、QGraphicsItem 渲染、序列化骨架、撤销/重做" "Python library" "External"
        }

        // ═══════════════════════════════════════════════════════════════
        // 外部软件系统
        // ═══════════════════════════════════════════════════════════════
        pythonRuntime = softwareSystem "Python 3.10.11" "CPython 解释器执行环境" "External"
        pyqt5Lib = softwareSystem "PyQt5 5.15.9" "Qt 5.15 的 Python 绑定，提供 GUI 框架和信号-槽机制" "External"
        numpyLib = softwareSystem "numpy" "数值计算库，用于波形数据处理" "External"

        // ═══════════════════════════════════════════════════════════════
        // 关系定义
        // ═══════════════════════════════════════════════════════════════

        // 人员 → 系统
        user -> signalRouterGraph "创建和管理信号路由图" "鼠标拖放"

        // 系统 → 外部
        signalRouterGraph -> pythonRuntime "执行于" "CPython"
        signalRouterGraph -> pyqt5Lib "使用 GUI 框架和信号机制" "Python import"
        signalRouterGraph -> numpyLib "用于波形数据处理" "Python import"

        // 容器 → 外部
        desktopApp -> nodeeditor "继承并扩展场景图管理" "Python inheritance"

        // ── 组件间关系: 应用窗口 → 面板 ──
        mainWindow -> toolPanel "创建并管理工具面板 DockWidget"
        mainWindow -> loggerPanel "创建并管理日志面板 DockWidget"
        mainWindow -> subWindow "创建 MdiChild 标签页"

        // ── 组件间关系: 面板 → 注册中心 ──
        nodeTree -> nodeRegistry "遍历节点树，展示所有已注册节点"
        nodeTree -> tcpClient "拖放创建实例（同以下所有节点）"
        nodeTree -> oscilloscope "拖放创建实例"
        nodeTree -> parser4ch "拖放创建实例"

        // ── 组件间关系: 图编辑器 → 场景引擎 ──
        subWindow -> sceneBase "管理场景、拖放创建节点、右键菜单"
        subWindow -> nodeRegistry "通过 get_class_from_tppath() 查找节点类"
        subWindow -> globalSettings "监听 viewPortUpdateMode / connectionType 变化"
        globalSettings -> sceneBase "切换连接类型 → scene.reconnectAll()"

        // ── 组件间关系: 场景引擎内部 ──
        sceneBase -> nodeBase "管理节点生命周期（创建、删除、选中）"
        sceneBase -> edgeBase "管理边生命周期"
        sceneBase -> clipboard "复制粘贴时使用自定义反序列化"
        nodeBase -> graphNode "创建和管理图形项"
        nodeBase -> socketBase "管理输入/输出端口"
        nodeBase -> socketConf "读取端口配置"
        nodeBase -> contentBase "嵌入内容部件到节点"
        edgeBase -> graphEdge "委托绘制（贝塞尔/直线/直角）"
        edgeBase -> socketBase "连接两个端口"
        socketBase -> socketConf "读取 argsType 用于类型验证"
        nodeBase -> graphSocket "创建端口图形项"

        // ── 组件间关系: 节点注册 ──
        nodeRegistry -> nodeBase "注册节点类到 CONN_NODES 字典"
        nodeRegistry -> sceneBase "反序列化时通过 tppath 查找节点类"

        // ── 组件间关系: 节点库 ──
        tcpClient -> nodeBase "继承 ConnNode 基类"
        tcpClient -> contentBase "继承 ConnNodeContentWidget"
        oscilloscope -> nodeBase "继承 ConnNode 基类"
        oscilloscope -> contentBase "继承 ConnNodeContentWidget"
        oscilloscope -> utilsLayer "注册 QThread 到 ThreadManager"
        parser4ch -> nodeBase "继承 ConnNode 基类"
        parser4ch -> contentBase "继承 ConnNodeContentWidget"
        pwmController -> nodeBase "继承 ConnNode 基类"
        pwmController -> contentBase "继承 ConnNodeContentWidget"

        // ── 组件间关系: 信号连接（运行时数据流） ──
        tcpClient -> edgeBase "emit received(QByteArray) → ConnEdge 连接"
        tcpServer -> edgeBase "emit received/clientConnected/clientDisconnected"
        serialPort -> edgeBase "emit received(QByteArray)"
        textSender -> edgeBase "emit sendDataNotify(QByteArray) / sendTextNotify(str)"
        hexSender -> edgeBase "emit sendData(QByteArray)"
        sineWaveGen -> edgeBase "emit data(QByteArray)"
        parser1ch -> edgeBase "emit ch0(ndarray, gap, interval)"
        parser2ch -> edgeBase "emit ch0~ch1(ndarray, gap, interval)"
        parser4ch -> edgeBase "emit ch0~ch3(ndarray, gap, interval)"
        pwmController -> edgeBase "emit ch1_send~ch4_send(QByteArray)"
        edgeBase -> oscilloscope "信号跨线程投递 → worker.writeData()"
        edgeBase -> hexReceiver "信号投递 → receivedData(QByteArray)"
        edgeBase -> textReceiver "信号投递 → appendText(str)"
        edgeBase -> pwmController "信号投递 → handleChCtrl(dict) / handleResponse(QByteArray)"

        // ── 组件间关系: 工具层 ──
        utilsLayer -> subWindow "SimpleLogger 向日志面板输出消息"
        utilsLayer -> mainWindow "shutdown_all_threads() 在退出时调用"
        utilsLayer -> oscilloscope "ThreadManager 管理 QThread 生命周期"

        // ═══════════════════════════════════════════════════════════════
        // 部署模型
        // ═══════════════════════════════════════════════════════════════
        deploymentEnvironment "开发/部署环境" {
            deploymentNode "Windows 工作站" "Windows 10 或更新版" "OS" {
                deploymentNode "Python 3.10.11 解释器" "CPython 运行时" "Runtime" {
                    deploymentNode "信号路由图编辑器进程" "单一桌面 GUI 进程" "Process" {
                        containerInstance desktopApp
                    }
                }
                deploymentNode "Python site-packages" "第三方依赖库目录" "Libraries" {
                    containerInstance nodeeditor
                }
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // 视图定义
    // ═══════════════════════════════════════════════════════════════════

    views {
        theme default

        // ── Level 1: 系统上下文 ────────────────────────────────────
        systemContext signalRouterGraph "SystemContext" "系统上下文 — SignalRouterGraph 与用户及外部依赖的顶层交互" {
            include *
            autoLayout
        }

        // ── Level 2: 容器 ───────────────────────────────────────────
        container signalRouterGraph "Containers" "容器图 — 桌面应用 + nodeeditor 框架 + 外部依赖" {
            include *
            autoLayout
        }

        // ── Level 3: 组件 — 全景 ────────────────────────────────────
        component desktopApp "AllComponents" "全组件图 — 桌面应用内部所有组件一览" {
            include *
            autoLayout
        }

        // ── Level 3: 组件 — 核心引擎 ────────────────────────────────
        component desktopApp "CoreEngine" "核心引擎组件 — conn_base.py + conn_conf.py 类层次详图" {
            include graphNode graphEdge graphSocket nodeBase edgeBase sceneBase socketBase contentBase socketConf clipboard nodeRegistry
            autoLayout
        }

        // ── Level 3: 组件 — 节点库分类 ──────────────────────────────
        component desktopApp "NodeLibrary" "节点库详图 — 所有注册节点按功能分类" {
            include tcpClient tcpServer serialPort textSender hexSender sineWaveGen
            include oscilloscope hexReceiver textReceiver
            include parser1ch parser2ch parser4ch
            include pwmController protocolUtils
            include nodeBase contentBase
            autoLayout
        }

        // ── Level 3: 组件 — 窗口与面板 ──────────────────────────────
        component desktopApp "UIAndPanels" "窗口与面板 — 应用界面层组件" {
            include mainWindow subWindow toolPanel nodeTree globalSettings loggerPanel threadPanel sceneBase nodeRegistry
            autoLayout
        }

        // ── 动态视图: 典型数据流 ─────────────────────────────────────
        dynamic desktopApp "TypicalDataFlow" "典型数据流 — 从数据采集到示波器显示" {
            tcpClient -> edgeBase "TCP 接收数据后 emit received(QByteArray)" ""
            parser1ch -> edgeBase "协议解析后 emit ch0(ndarray, gap, interval)" ""
            parser2ch -> edgeBase "协议解析后 emit ch0~ch1" ""
            parser4ch -> edgeBase "协议解析后 emit ch0~ch3" ""
            pwmController -> edgeBase "PWM 控制指令 emit chN_send(QByteArray)" ""
            sineWaveGen -> edgeBase "正弦波数据 emit data(QByteArray)" ""
            edgeBase -> oscilloscope "信号通过 ConnEdge 跨线程投递到 worker.writeData()" ""
            edgeBase -> hexReceiver "信号投递到 receivedData() 显示 Hex" ""
            edgeBase -> textReceiver "信号投递到 appendText() 显示文本" ""
            edgeBase -> pwmController "信号投递 (dict/QByteArray 控制指令)" ""
            oscilloscope -> utilsLayer "QThread 生命周期通过 ThreadManager 管理" ""

            autoLayout tb
        }

        // ── 部署视图 ────────────────────────────────────────────────
        deployment signalRouterGraph "开发/部署环境" "Deployment" "Windows 桌面部署拓扑" {
            include *
            autoLayout
        }

        // ── 全局样式 ─────────────────────────────────────────────────
        styles {
            element "Person" {
                shape Person
                background #08427B
                color #ffffff
            }
            element "Software System" {
                background #1168BD
                color #ffffff
            }
            element "Container" {
                background #438DD5
                color #ffffff
            }
            element "External" {
                background #999999
                color #ffffff
            }
            element "UI" {
                background #50B86C
                color #ffffff
            }
            element "Core" {
                background #4A90D9
                color #ffffff
            }
            element "Node" {
                background #D2A554
                color #000000
            }
            element "Component" {
                background #85BBF0
                color #000000
                fontSize 11
            }
        }
    }
}
