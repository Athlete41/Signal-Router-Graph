from qtpy.QtWidgets import QWidget, QVBoxLayout

from conn_view_setting_panel import QDMViewSettingPanel
from conn_nodes_panel import QDMNodesPanel
from conn_thread_panel import QDMThreadPanel



class QDMToolPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        self.threadPanel = QDMThreadPanel(self)
        self.viewSettingPanel = QDMViewSettingPanel(self)
        self.nodesPanel = QDMNodesPanel(self)
        
        layout.addWidget(self.threadPanel)
        layout.addWidget(self.viewSettingPanel)
        layout.addWidget(self.nodesPanel)


   