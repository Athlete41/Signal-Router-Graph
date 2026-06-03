import os, sys
from qtpy.QtWidgets import QApplication


from conn_window import ConnectionWindow


if __name__ == '__main__':
    app = QApplication(sys.argv)

    # print(QStyleFactory.keys())
    app.setStyle('Fusion')

    wnd = ConnectionWindow()
    wnd.show()

    sys.exit(app.exec_())
