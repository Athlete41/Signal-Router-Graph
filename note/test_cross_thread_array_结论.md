# PyQt5 跨线程信号传递行为 — 实证结论

`note/test_cross_thread_array.py`，Python 3.10.11 + PyQt5 5.15.9 实测结果。

Auto/Queued/BlockingQueued 三种跨线程连接方式行为一致。

| 信号类型 | 传的值类型 | 跨线程行为 |
|----------|-----------|-----------|
| `pyqtSignal(list)` | list | 深拷贝 |
| `pyqtSignal(dict)` | dict | 引用传递 |
| `pyqtSignal(object)` | list | 引用传递 |
| `pyqtSignal(object)` | dict | 引用传递 |
| `pyqtSignal(object)` | numpy.ndarray | 引用传递 |
