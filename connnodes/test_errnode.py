from conn_conf import register_node
from conn_base import ConnNode, ConnSocketConf

@register_node()
class Test_Error_UnregisteredSignalNode(ConnNode):
    tppath = ("测试", "异常-未注册信号")
    icon = "icons/emitter.png"
    name = "异常-未注册信号"
    tooltip = "未调用 self.registerSignal 注册信号"
    conn_title = "异常-未注册信号"


    def __init__(self, scene):
        super().__init__(scene, 
            signalsConf=[
                ConnSocketConf(
                    socketType=2,
                    key="test_signal",
                    argsType=(str,)
                )
            ],
        )