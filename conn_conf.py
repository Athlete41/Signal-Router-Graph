LISTBOX_MIMETYPE = "application/x-item"

VERSION = "1.0.0"

CONN_NODES: dict[tuple[str], type] = {
}


ALL_NODES_DISPLAY: dict[tuple[str], dict[str, object]] = {
}


def register_node_now(tppath: tuple[str], class_reference):
    if not isinstance(tppath, tuple) or any(not isinstance(p, str) for p in tppath):
        raise TypeError("无效路径, 必须是非空字符串元组: '%s'" % tppath)
    else:
        if tppath in CONN_NODES:
            raise ValueError("路径 '%s' 已注册" % tppath)
        
        CONN_NODES[tppath] = class_reference

def register_node(tppath: tuple[str] = None):
    def decorator(original_class):
        path = tppath
        if path is None and original_class.tppath is None:
            raise ValueError("节点路径不能为空")
        elif path is None:
            path = original_class.tppath
        elif original_class.tppath is None:
            original_class.tppath = path
        elif path != original_class.tppath:
            raise ValueError("节点路径不能与类属性不同")

        register_node_now(path, original_class)
        return original_class
    return decorator

def get_class_from_tppath(tppath: tuple[str]):
    if not isinstance(tppath, tuple) or any(not isinstance(p, str) for p in tppath):
        raise TypeError("无效路径, 必须是非空字符串元组: '%s'" % tppath)
    else:
        if tppath not in CONN_NODES:
            raise ValueError("路径 '%s' 未注册" % tppath)
        
        return CONN_NODES[tppath]

def set_node_display(tppath: tuple[str], 
                     name: str = None, 
                     tooltip: str = None, 
                     icon: str = None
                     ):
    if not isinstance(tppath, tuple) or any(not isinstance(p, str) for p in tppath):
        raise TypeError("无效路径, 必须是非空字符串元组: '%s'" % tppath)
  
    if name is not None and not isinstance(name, str):
        raise TypeError("无效名称, 必须是字符串 或 None: '%s'" % name)
    
    if tooltip is not None and not isinstance(tooltip, str):
        raise TypeError("无效提示, 必须是字符串 或 None: '%s'" % tooltip)
    
    if icon is not None and not isinstance(icon, str):
        raise TypeError("无效图标, 必须是字符串 或 None: '%s'" % icon)

    if tppath not in ALL_NODES_DISPLAY:
        ALL_NODES_DISPLAY[tppath] = {}

    new = {}
    if name is not None:
        new["name"] = name
    if tooltip is not None:
        new["tooltip"] = tooltip
    if icon is not None:
        new["icon"] = icon

    ALL_NODES_DISPLAY[tppath].update(new)


from qtpy.QtCore import QObject, QMutex, QMutexLocker, Qt
from PyQt5.QtCore import pyqtSignal
from qtpy.QtWidgets import QGraphicsView

class GlobalSettingManager(QObject):
    """
    全局配置管理器 (全局单例，长期存活)
    """
    viewPortUpdateModeChanged = pyqtSignal(int)
    connectionTypeChanged = pyqtSignal(int)

    _instance = None
    _mutex = QMutex()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def viewPortUpdateMode(self):
        with QMutexLocker(self._mutex):
            return self._viewPortUpdateMode
        
    @property
    def connectionType(self):
        with QMutexLocker(self._mutex):
            return self._connectionType
        
    @viewPortUpdateMode.setter
    def viewPortUpdateMode(self, value):
        if not isinstance(value, int):
            raise TypeError("viewPortUpdateMode 只接收 int 类型")
        
        with QMutexLocker(self._mutex):
            self._viewPortUpdateMode = value

        self.viewPortUpdateModeChanged.emit(value)

    @connectionType.setter
    def connectionType(self, value):
        if not isinstance(value, int):
            raise TypeError("connectionType 只接收 int 类型")
        
        with QMutexLocker(self._mutex):
            self._connectionType = value

        self.connectionTypeChanged.emit(value)


    def __init__(self, parent=None):
        super().__init__(parent)
        self._viewPortUpdateMode = QGraphicsView.FullViewportUpdate
        self._connectionType = Qt.AutoConnection



# import all nodes and register them
from connnodes import *
