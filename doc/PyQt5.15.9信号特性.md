
# 关于此版本 PyQt5 信号重要特性描述

signal.disconnect(slot): 
    这只能一次性断开一个连接, 而是一个一个断开并且遵循后进先出的原则
    当 slot 没有连接时, 抛出的是 TypeError 而不是 RuntimeError

signal.disconnect(): 
    这会断开所有连接, 无任何槽连接到信号时同样抛出 TypeError 而不是 RuntimeError

signal.emit(*args) 与 signal.connect(slot, connection_type=Qt.AutoConnection): 
    详见 PyQt5.15.9 文档 与 ./test_emit.py 实测
    关于投递策略与执行, 调用 signal.connect 时会生成槽对象亲和线程的快照, 后续又会根据执行投递的线程来选择策略与执行，
    所以 `快照` 和 `投递线程` 很重要, 将以此对 SignalRelay 和 SignalDynamic 的行为进行分析