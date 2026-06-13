from PyQt5.QtWidgets import QTextBrowser, QWidget, QVBoxLayout, QPushButton


class QDMSimpleLoggerPanel(QWidget):
    def __init__(self, parent = None):
        super().__init__(parent)

        clear_button = QPushButton("清除")
        self.text_browser = QTextBrowser(self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.text_browser)
        layout.addWidget(clear_button)
        clear_button.clicked.connect(self.text_browser.clear)
        

    def updateNewMsg(self, msg: str) -> None:
        self.text_browser.append(msg)