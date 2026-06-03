版本: 0.9.15

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

# 场景
此框架默认使用`Scene`类管理场, 使用一下代码自定义场景类:

```python
class MyScene(Scene):
    ...

class MyNodeEditorWidget(NodeEditorWidget):
    Scene_class = MyScene
```
## 自定义 Scene 的用途
- 需要使用自定义连接类:
默认`scene`使用`Edge`类, 并且没有提供一个方法来指定使用的连接。
这是内部代码, 其注释指出:若是要使用自定义连接, 则需要重写`getEdgeClass`方法.

```python
class Scene(Serializable):
    ...
    def getEdgeClass(self):
        """Return the class representing Edge. Override me if needed"""
        return Edge
```

## 连接
此版本对自定义连接的支持较弱，如果需要自定义连接需要更改较多东西

## 连接验证
相关内部代码如下, 这非常简单, 使用`Edge.registerEdgeValidator`方法注册验证器。对所有连接有效。
```python
class Edge(Serializable):
    ...
    @classmethod
    def registerEdgeValidator(cls, validator_callback: 'function'):
        """Register Edge Validator Callback

        :param validator_callback: A function handle to validate Edge
        :type validator_callback: `function`
        """
        cls.edge_validators.append(validator_callback)

    @classmethod
    def validateEdge(cls, start_socket: 'Socket', end_socket: 'Socket') -> bool:
        """Validate Edge agains all registered `Edge Validator Callbacks`

        :param start_socket: Starting :class:`~nodeeditor.node_socket.Socket` of Edge to check
        :type start_socket: :class:`~nodeeditor.node_socket.Socket`
        :param end_socket: Target/End :class:`~nodeeditor.node_socket.Socket` of Edge to check
        :type end_socket: :class:`~nodeeditor.node_socket.Socket`
        :return: ``True`` if the Edge is valid or ``False`` if not
        :rtype: ``bool``
        """
        for validator in cls.getEdgeValidators():
            if not validator(start_socket, end_socket):
                return False
        return True
```

## 连接绘制

想要改变需要自定义连接图形，需要自定义 `MyGraphicsEdge` 类，并且在自定义的 `Edge` 类中重写 `getGraphicsEdgeClass` 指定。

示例代码:
```python
MyEdge(Edge):
    def getGraphicsEdgeClass(self):
        return MyGraphicsEdge

MyGraphicsEdge(QDMGraphicsEdge):
    ...
```


## 自定义连接的粘贴问题

通过调试器发现，复制粘贴的过程为先序列化再反序列化，序列化没有问题可以进入我们重写的入口，但是反序列化不行，
反序列化默认使用 `Edge` 类, 需要先自定义一个粘贴板类再在自定义场景类中指定。


```python

class MyEdge(Edge):
    ...

class MySceneClipboard(SceneClipboard):
    def deserializeFromClipboard(self, data: dict, *args, **kwargs):
        ... # 较长的原逻辑
        if 'edges' in data:
            for edge_data in data['edges']:
                new_edge = MyEdge(self.scene) # 在这里改成你的
                new_edge.deserialize(edge_data, hashmap, restore_id=False, *args, **kwargs)

        ... # 原逻辑

class MyScene(Scene):
    clipboardClass = MySceneClipboard

```