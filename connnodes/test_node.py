from conn_conf import register_node, set_node_display
from conn_node_base import ConnNode, ConnGraphicsNode, ConnContent


@register_node(("测试目录", "测试子目录", "测试节点"))
class ConnNode_Test(ConnNode):
    tppath = ("测试目录", "测试子目录", "测试节点")
    icon = "icons/in.png"
    name = "测试节点"
    tooltip = "测试节点的提示"
    
    conn_title = "测试节点的标题"

    def __init__(self, scene):
        super().__init__(scene, inputs=[], outputs=[3])
        self.eval()

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