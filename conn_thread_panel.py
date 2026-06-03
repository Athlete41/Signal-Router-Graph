
from qtpy.QtWidgets import QWidget, QVBoxLayout
from qtpy.QtWidgets import QLabel
from conn_utils import ThreadManager


class QDMThreadPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        self.title = QLabel("线程数量: 0", self)
        

        ThreadManager.instance().list_changed_notify.connect(self.set_thread_count)

        self.setLayout(layout)
        layout.addWidget(self.title)

    def set_thread_count(self):
        self.title.setText(f"线程数量: {ThreadManager.instance().get_count()}")


