LISTBOX_MIMETYPE = "application/x-item"


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

def register_node(tppath: tuple[str]):
    def decorator(original_class):
        register_node_now(tppath, original_class)
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
                     name: str, 
                     tooltip: str, 
                     icon: str = None
                     ):
    if not isinstance(tppath, tuple) or any(not isinstance(p, str) for p in tppath):
        raise TypeError("无效路径, 必须是非空字符串元组: '%s'" % tppath)
  
    if not isinstance(name, str):
        raise TypeError("无效名称, 必须是字符串: '%s'" % name)
    
    if not isinstance(tooltip, str):
        raise TypeError("无效提示, 必须是字符串: '%s'" % tooltip)
    
    if not isinstance(icon, str):
        raise TypeError("无效图标, 必须是字符串: '%s'" % icon)

    if tppath not in ALL_NODES_DISPLAY:
        ALL_NODES_DISPLAY[tppath] = {}

    ALL_NODES_DISPLAY[tppath].update({
        "name": name,
        "tooltip": tooltip,
        "icon": icon
    })


# import all nodes and register them
from connnodes import *
