from conn_conf import register_node
from conn_node_base import ConnNode


@register_node(("测试", "异常-绑定未对齐"))
class Test_Error_BindNotAlignedNode(ConnNode):
    tppath = ("测试", "异常-绑定未对齐")
    icon = "icons/emitter.png"
    name = "异常-绑定未对齐"
    tooltip = "outputs 和 outputBinds 数量不一致"
    conn_title = "异常-绑定未对齐"


    def __init__(self, scene):
        super().__init__(scene, 
            inputs=[], 
            inputBinds=[],
            inputDisplays=[],

            outputs=[2], 
            outputBinds=[],
            outputDisplays=[],
        )


@register_node(("测试", "异常-未注册信号"))
class Test_Error_UnregisteredSignalNode(ConnNode):
    tppath = ("测试", "异常-未注册信号")
    icon = "icons/emitter.png"
    name = "异常-未注册信号"
    tooltip = "未调用 self.registerSignal 注册信号"
    conn_title = "异常-未注册信号"


    def __init__(self, scene):
        super().__init__(scene, 
            inputs=[], 
            inputBinds=[],
            inputDisplays=[],

            outputs=[2], 
            outputBinds=["test_signal"],
            outputDisplays=[],
        )