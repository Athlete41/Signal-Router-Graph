# from qtpy.QtWidgets import QTreeWidget, QTreeWidgetItem, QApplication, QAbstractItemView
# from qtpy.QtGui import QIcon, QPixmap
# from qtpy.QtCore import Qt, QSize

# from pathlib import Path


# icon = QIcon(str(Path(__file__).parent / "icon" / "add.png"))


# app = QApplication([])

# class TestTree(QTreeWidget):
#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self.setIconSize(QSize(32, 32))
#         self.setSelectionMode(QAbstractItemView.SingleSelection)
#         self.setDragEnabled(True)
#         self.setColumnCount(2)
#         self.setHeaderLabels(["col1", "col2"])

#     # def startDrag(self, supportedActions):
#     #     print(546565656)


# treeWidget = TestTree()
# treeWidget.setIconSize(QSize(32, 32))

# items = []
# for i in range(10):
#     item = QTreeWidgetItem()
#     item.setText(0, f"item: {i}")
#     item.setText(1, f"item: {i}")
#     item.setToolTip(0, f"fucking tooltip: {i}")
#     item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
#     child = QTreeWidgetItem()
#     item.addChild(child)
#     items.append(item)

# treeWidget.insertTopLevelItems(0, items)
# treeWidget.insertTopLevelItems(1, items)

# treeWidget.show()



# app.exec_()
import json

print(tuple([1,2,3]))