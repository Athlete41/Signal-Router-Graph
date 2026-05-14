from conn_conf import register_node, set_node_display
from conn_node_base import ConnNode, ConnGraphicsNode, ConnContent
from logger import SimpleLogger, LEVEL, logging

if LEVEL <= logging.DEBUG:
    @register_node(("测试目录", "测试子目录", "测试节点1"))
    class ConnNode_Test(ConnNode):
        tppath = ("测试目录", "测试子目录", "测试节点1")
        icon = "icons/in.png"
        name = "测试节点1"
        tooltip = "测试节点1的提示"
        
        conn_title = "测试节点1的标题"

        def __init__(self, scene):
            super().__init__(scene, inputs=[], outputs=[])
            SimpleLogger.instance().info("测试节点1创建成功！")

        def initInnerClasses(self):
            self.content = ConnContent(self)
            self.grNode = ConnGraphicsNode(self)


    set_node_display(
        tppath=("测试目录", ), 
        tooltip="测试目录的提示", 
        icon="icons/sub.png")

    set_node_display(
        tppath=("测试目录", "测试子目录"), 
        tooltip="测试提示", 
        icon="icons/sub.png"
    )

    @register_node(("测试目录", "测试子目录", "测试节点2"))
    class ConnNode_Test(ConnNode):
        tppath = ("测试目录", "测试子目录", "测试节点2")
        icon = "icons/in.png"
        name = "测试节点2"
        tooltip = "测试节点2的提示"
        
        conn_title = "测试节点2的标题"

        def __init__(self, scene):
            super().__init__(scene, inputs=[], outputs=[])
            SimpleLogger.instance().info("测试节点2创建成功！")

        def initInnerClasses(self):
            self.content = ConnContent(self)
            self.grNode = ConnGraphicsNode(self)