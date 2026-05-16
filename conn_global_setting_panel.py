from qtpy.QtGui import QIcon
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from qtpy.QtWidgets import QComboBox, QGraphicsView, QLabel
from PyQt5.QtCore import pyqtSignal

from conn_conf import GlobalSettingManager
from conn_utils import easyError



class QDMGlobalSettingPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        title = QLabel("全局选项", self)

        layout_viewUpdateMode = QHBoxLayout()
        viewUpdateModeSelecterLable = QLabel("视图更新模式", self)
        self.viewUpdateModeSelecter = QComboBox(self)

        layout_connectType = QHBoxLayout()
        connectTypeSelecterLabel = QLabel("信号连接类型", self)
        self.connectTypeSelecter = QComboBox(self)
        
        self.setLayout(layout)
        layout.addWidget(title)

        layout_viewUpdateMode.addWidget(viewUpdateModeSelecterLable)
        layout_viewUpdateMode.addWidget(self.viewUpdateModeSelecter)
        layout.addLayout(layout_viewUpdateMode)

        layout_connectType.addWidget(connectTypeSelecterLabel)
        layout_connectType.addWidget(self.connectTypeSelecter)
        layout.addLayout(layout_connectType)


        self.viewUpdateModeSelecter.addItem(QIcon("icons/run.png"), "全视更新")
        self.viewUpdateModeSelecter.addItem("最小更新")
        self.viewUpdateModeSelecter.addItem("智能更新")
        self.viewUpdateModeSelecter.addItem("边界更新")
        self.viewUpdateModeSelecter.addItem(QIcon("icons/freeze.png"), "无更新")

        self.viewUpdateModeSelecter.setItemData(0, QGraphicsView.FullViewportUpdate, Qt.UserRole)
        self.viewUpdateModeSelecter.setItemData(1, QGraphicsView.MinimalViewportUpdate, Qt.UserRole)
        self.viewUpdateModeSelecter.setItemData(2, QGraphicsView.SmartViewportUpdate, Qt.UserRole)
        self.viewUpdateModeSelecter.setItemData(3, QGraphicsView.BoundingRectViewportUpdate, Qt.UserRole)
        self.viewUpdateModeSelecter.setItemData(4, QGraphicsView.NoViewportUpdate, Qt.UserRole)

        toolTip0 = """当场景的任何可见部分发生变化或重新暴露时，QGraphicsView 会更新整个视口。
当 QGraphicsView 花费更多时间确定要绘制的内容（而非实际绘制的时间）时，这种方法是最快的（例如，当非常多的小型图元被反复更新时）。
对于不支持部分更新的视口（例如 QOpenGLWidget）以及需要禁用滚动优化的视口，这是首选的更新模式。"""

        toolTip1 = """QGraphicsView 会确定需要重绘的最小视口区域，通过避免重绘未发生变化的区域来最小化绘制时间。
这是 QGraphicsView 的默认模式。虽然这种方式通常能提供最佳性能，但如果场景中存在许多小的可见变化，
QGraphicsView 最终可能会花费更多时间去寻找最小区域，而不是实际进行绘制。"""

        toolTip2 = """QGraphicsView 会尝试通过分析需要重绘的区域来找到最优的更新模式。"""
        toolTip3 = """视口中所有变化的边界矩形将被重绘。这种模式的优点是 QGraphicsView 只搜索一个变化区域，
从而最小化确定需要重绘什么的时间。缺点是未发生变化的区域也需要被重绘。"""

        toolTip4 = """当场景发生变化时，QGraphicsView 永远不会更新它的视口；用户需要控制所有更新。
此模式禁用了 QGraphicsView 中所有（可能较慢的）图元可见性检测，适用于需要固定帧率、或者视口由外部以其他方式更新的场景。"""

        self.viewUpdateModeSelecter.setItemData(0, toolTip0, Qt.ToolTipRole)
        self.viewUpdateModeSelecter.setItemData(1, toolTip1, Qt.ToolTipRole)
        self.viewUpdateModeSelecter.setItemData(2, toolTip2, Qt.ToolTipRole)
        self.viewUpdateModeSelecter.setItemData(3, toolTip3, Qt.ToolTipRole)
        self.viewUpdateModeSelecter.setItemData(4, toolTip4, Qt.ToolTipRole)


        self.connectTypeSelecter.addItem("Auto 类型")
        self.connectTypeSelecter.addItem("Queued 类型")
        self.connectTypeSelecter.setItemData(0, Qt.AutoConnection, Qt.UserRole)
        self.connectTypeSelecter.setItemData(1, Qt.QueuedConnection, Qt.UserRole)
        

        idx = self.viewUpdateModeSelecter.findData(GlobalSettingManager.instance().viewPortUpdateMode, Qt.UserRole)
        if idx == -1: 
            easyError(f"未知视图更新模式: {GlobalSettingManager.instance().viewPortUpdateMode}")
        else:
            self.viewUpdateModeSelecter.setCurrentIndex(idx)
        self.viewUpdateModeSelecter.currentIndexChanged.connect(self.onViewUpdateModeSelecterChanged)


        idx = self.connectTypeSelecter.findData(GlobalSettingManager.instance().connectionType, Qt.UserRole)
        if idx == -1: 
            easyError(f"未知连接类型: {GlobalSettingManager.instance().connectionType}")
        else:
            self.connectTypeSelecter.setCurrentIndex(idx)
        self.connectTypeSelecter.currentIndexChanged.connect(self.onViewUpdateModeSelecterChanged)

        self.setObjectName("ViewSettingPanel")
        self.viewUpdateModeSelecter.setObjectName("ViewUpdateModeSelecter")
        self.connectTypeSelecter.setObjectName("ConnectTypeSelecter")
        # TODO 暂时没找到细致修改全局样式的方法, 这里先简单处理
        self.setStyleSheet("""
QComboBox#ViewUpdateModeSelecter {
    background-color: #202020;
    color: #e0e0e0;
}
                           
QComboBox#ConnectTypeSelecter {
    background-color: #202020;
    color: #e0e0e0;
}
""")

    def onViewUpdateModeSelecterChanged(self):
        GlobalSettingManager.instance().viewPortUpdateMode = self.viewUpdateModeSelecter.currentData(Qt.UserRole)

    def onConnectTypeSelecterChanged(self):
        GlobalSettingManager.instance().connectionType = self.connectTypeSelecter.currentData(Qt.UserRole)
