from qtpy.QtWidgets import QWidget, QVBoxLayout

from conn_global_setting_panel import QDMGlobalSettingPanel
from conn_nodes_panel import QDMNodesPanel
from conn_thread_panel import QDMThreadPanel



class QDMToolPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        self.threadPanel = QDMThreadPanel(self)
        self.globalSettingPanel = QDMGlobalSettingPanel(self)
        self.nodesPanel = QDMNodesPanel(self)
        
        layout.addWidget(self.threadPanel)
        layout.addWidget(self.globalSettingPanel)
        layout.addWidget(self.nodesPanel)


   