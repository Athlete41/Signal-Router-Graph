from qtpy.QtGui import QPixmap, QIcon, QDrag
from qtpy.QtCore import QSize, Qt, QByteArray, QDataStream, QMimeData, QIODevice, QPoint
from qtpy.QtWidgets import QTreeWidget, QAbstractItemView, QTreeWidgetItem

from conn_conf import CONN_NODES, ALL_NODES_DISPLAY, get_class_from_tppath, LISTBOX_MIMETYPE
from nodeeditor.utils import dumpException


class QDMDragTreebox(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.item_map = {}
        self.initUI()
        

    def initUI(self):
        # init
        self.setIconSize(QSize(32, 32))
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragEnabled(True)

        self.addMyItems()

    def addMyItems(self):
        keys = list(CONN_NODES.keys())
        keys.sort()
        for tpkey in keys:
            if not tpkey: continue

            conn_cls = get_class_from_tppath(tpkey)
            parent_node = self
            for i in range(len(tpkey)):
                subkey = tpkey[0:i+1]
                if subkey not in self.item_map:
                    subitem = QTreeWidgetItem()
                    self.item_map[subkey] = subitem
                    if parent_node is self:
                        self.addTopLevelItem(subitem)
                    else:
                        parent_node.addChild(subitem)
                    display_conf = ALL_NODES_DISPLAY.get(subkey, {})

                    subitem.setText(0, display_conf.get("name", subkey[-1]))
                    subitem.setToolTip(0, display_conf.get("tooltip", ""))
                    subitem.setIcon(0, QIcon(display_conf.get("icon", "")))
                    subitem.setSizeHint(0, QSize(32, 32))

                parent_node = self.item_map[subkey]

            conn_item: QTreeWidgetItem = parent_node
            
            pixmap = QPixmap(conn_cls.icon)
            conn_item.setText(0, conn_cls.name)
            conn_item.setToolTip(0, conn_cls.tooltip)
            conn_item.setIcon(0, QIcon(pixmap))
            conn_item.setSizeHint(0, QSize(32, 32))

            conn_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)

            # setup data
            conn_item.setData(0, Qt.UserRole, pixmap)
            conn_item.setData(0, Qt.UserRole + 1, tpkey)


 
    def startDrag(self, *args, **kwargs):
        try:
            item = self.currentItem()
            tppath = item.data(0, Qt.UserRole + 1)

            if not tppath: 
                return
            
            pixmap = QPixmap(item.data(0, Qt.UserRole))


            itemData = QByteArray()
            dataStream = QDataStream(itemData, QIODevice.WriteOnly)
            dataStream << pixmap

            dataStream.writeQStringList(list(tppath))
            dataStream.writeQString(item.text(0))

            mimeData = QMimeData()
            mimeData.setData(LISTBOX_MIMETYPE, itemData)

            drag = QDrag(self)
            drag.setMimeData(mimeData)
            drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
            drag.setPixmap(pixmap)

            drag.exec_(Qt.MoveAction)

        except Exception as e: dumpException(e)