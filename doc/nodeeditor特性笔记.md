# 图的反序列化

## 框架如何找到对应的节点类?

- 从 examples\example_calculator\main.py 中单步调试: 
框架在反序列化节点时, 会调用`scene.getNodeClassFromData`方法, 
如果`scene.node_class_selector` 为`None`, 则会返回`Node`类的实例.

`scene.getNodeClassFromData` 具体实现:
```python
def getNodeClassFromData(self, data: dict) -> 'Node class instance':
    """
    ...
    """
    return Node if self.node_class_selector is None else self.node_class_selector(data)
```

## 如何自定义类查询?
1. 重写`scene.getNodeClassFromData`方法. (不推荐)
2. 调用`scene.setNodeClassSelector(class_selecting_function: 'functon')`方法. (推荐)

- 具体工作: 
```python
CLASS = {}

# 需使用 scene.setNodeClassSelector 方法设置.
def class_selecting_function(self, data):
    if '类的标识符' not in data: return Node
    return CLASS[data['类的标识符']]

class MyNode(Node):
    # 节点的序列化. 
    def serialize(self):
        res = super().serialize()
        res['类的标识符'] = self.__class__.__name__
        return res

CLASS['MyNode'] = MyNode
```
