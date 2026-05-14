from conn_conf import register_node
from conn_node_base import ConnNode, ConnGraphicsNode, ConnContent


@register_node(("测试目录", "测试节点"))
class ConnNode_Test(ConnNode):
    tppath = ("测试目录", "测试节点")
    icon = "icons/in.png"
    title = "测试节点的标题"
    content_label_objname = "conn_node_test"

    def __init__(self, scene):
        super().__init__(scene, inputs=[], outputs=[3])
        self.eval()

    def initInnerClasses(self):
        self.content = ConnContent(self)
        self.grNode = ConnGraphicsNode(self)