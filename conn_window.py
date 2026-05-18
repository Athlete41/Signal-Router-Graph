import os
from qtpy.QtGui import QIcon, QKeySequence
from qtpy.QtWidgets import QMdiArea, QWidget, QDockWidget, QAction, QMessageBox, QFileDialog
from qtpy.QtCore import Qt, QSignalMapper, QSettings

from nodeeditor.utils import loadStylesheets
from nodeeditor.node_editor_window import NodeEditorWindow
from conn_sub_window import ConnSubWindow
from conn_tool_panel import QDMToolPanel
from nodeeditor.utils import dumpException, pp
from conn_conf import CONN_NODES, VERSION, GlobalSettingManager
from conn_utils import SimpleLogger, SimpleLoggerBrowser, logger, LEVEL, logging, ThreadManager, easyError


# images for the dark skin
import qss.nodeeditor_dark_resources


DEBUG = True


class ConnectionWindow(NodeEditorWindow):

    def initUI(self):
        self.name_company = '未知'
        self.name_product = '信号路由图编辑器'

        self.stylesheet_filename = os.path.join(os.path.dirname(__file__), "qss/nodeeditor.qss")
        loadStylesheets(
            os.path.join(os.path.dirname(__file__), "qss/nodeeditor-dark.qss"),
            self.stylesheet_filename
        )

        self.empty_icon = QIcon(".")

        SimpleLogger.instance()
        ThreadManager.instance()

        logger.debug("注册的节点:")
        logger.debug(CONN_NODES)

        self.mdiArea = QMdiArea()
        self.mdiArea.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.mdiArea.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.mdiArea.setViewMode(QMdiArea.ViewMode.TabbedView)
        self.mdiArea.setDocumentMode(True)
        self.mdiArea.setTabsClosable(True)
        self.mdiArea.setTabsMovable(True)
        self.setCentralWidget(self.mdiArea)

        self.mdiArea.subWindowActivated.connect(self.updateMenus)

        self.createToolPanelDock()
        self.createSimpleLoggerDock()
        self.createActions()
        self.createMenus()
        self.createToolBars()
        self.createStatusBar()
        self.updateMenus()

        self.readSettings()

        self.setWindowTitle("信号路由图编辑器")
        
        SimpleLogger.instance().debug("注册的节点:")
        SimpleLogger.instance().debug(CONN_NODES)


    def closeEvent(self, event):
        self.mdiArea.closeAllSubWindows()
        if self.mdiArea.currentSubWindow():
            event.ignore()
        else:
            self.writeSettings()
            event.accept()
            # hacky fix for PyQt 5.14.x
            import sys
            sys.exit(0)


    def createActions(self):
        super().createActions()

        self.actClose = QAction("Cl&ose", self, statusTip="Close the active window", triggered=self.mdiArea.closeActiveSubWindow)
        self.actCloseAll = QAction("Close &All", self, statusTip="Close all the windows", triggered=self.mdiArea.closeAllSubWindows)
        self.actTile = QAction("&Tile", self, statusTip="Tile the windows", triggered=self.mdiArea.tileSubWindows)
        self.actCascade = QAction("&Cascade", self, statusTip="Cascade the windows", triggered=self.mdiArea.cascadeSubWindows)
        self.actNext = QAction("Ne&xt", self, shortcut=QKeySequence.NextChild, statusTip="Move the focus to the next window", triggered=self.mdiArea.activateNextSubWindow)
        self.actPrevious = QAction("Pre&vious", self, shortcut=QKeySequence.PreviousChild, statusTip="Move the focus to the previous window", triggered=self.mdiArea.activatePreviousSubWindow)

        self.actSeparator = QAction(self)
        self.actSeparator.setSeparator(True)

        self.actAbout = QAction("&About", self, statusTip="Show the application's About box", triggered=self.about)

        # 更改重做快捷键为 Ctrl+Y
        self.actRedo.deleteLater()
        self.actRedo = QAction('&Redo', self, shortcut='Ctrl+Y', statusTip="Redo last operation", triggered=self.onEditRedo)

    def getCurrentNodeEditorWidget(self):
        """ we're returning NodeEditorWidget here... """
        activeSubWindow = self.mdiArea.activeSubWindow()
        if activeSubWindow:
            return activeSubWindow.widget()
        return None

    def onFileNew(self):
        try:
            subwnd = self.createMdiChild()
            subwnd.widget().fileNew()
            subwnd.show()
        except Exception as e: dumpException(e)


    def onFileOpen(self):
        fnames, filter = QFileDialog.getOpenFileNames(self, 'Open graph from file', self.getFileDialogDirectory(), self.getFileDialogFilter())

        try:
            for fname in fnames:
                if fname:
                    existing = self.findMdiChild(fname)
                    if existing:
                        self.mdiArea.setActiveSubWindow(existing)
                    else:
                        # we need to create new subWindow and open the file
                        nodeeditor = ConnSubWindow()
                        if nodeeditor.fileLoad(fname):
                            self.statusBar().showMessage("File %s loaded" % fname, 5000)
                            nodeeditor.setTitle()
                            subwnd = self.createMdiChild(nodeeditor)
                            subwnd.show()
                        else:
                            nodeeditor.close()
        except Exception as e: dumpException(e)


    def about(self):
        QMessageBox.about(self, "关于信号路由图编辑器",
                f"改造自 nodeeditor 下的 example_calculator, 与其不同的是, 此编辑器运行逻辑依赖于信号的连接, 而不是直接在节点上执行计算, 这是为实时性而准备的。\n版本: {VERSION}")

    def createMenus(self):
        super().createMenus()

        self.windowMenu = self.menuBar().addMenu("&Window")
        self.updateWindowMenu()
        self.windowMenu.aboutToShow.connect(self.updateWindowMenu)

        self.menuBar().addSeparator()

        self.helpMenu = self.menuBar().addMenu("&Help")
        self.helpMenu.addAction(self.actAbout)

        self.editMenu.aboutToShow.connect(self.updateEditMenu)

    def updateMenus(self):
        # print("update Menus")
        active = self.getCurrentNodeEditorWidget()
        hasMdiChild = (active is not None)

        self.actSave.setEnabled(hasMdiChild)
        self.actSaveAs.setEnabled(hasMdiChild)
        self.actClose.setEnabled(hasMdiChild)
        self.actCloseAll.setEnabled(hasMdiChild)
        self.actTile.setEnabled(hasMdiChild)
        self.actCascade.setEnabled(hasMdiChild)
        self.actNext.setEnabled(hasMdiChild)
        self.actPrevious.setEnabled(hasMdiChild)
        self.actSeparator.setVisible(hasMdiChild)

        self.updateEditMenu()

    def updateEditMenu(self):
        try:
            # print("update Edit Menu")
            active = self.getCurrentNodeEditorWidget()
            hasMdiChild = (active is not None)

            self.actPaste.setEnabled(hasMdiChild)

            self.actCut.setEnabled(hasMdiChild and active.hasSelectedItems())
            self.actCopy.setEnabled(hasMdiChild and active.hasSelectedItems())
            self.actDelete.setEnabled(hasMdiChild and active.hasSelectedItems())

            self.actUndo.setEnabled(hasMdiChild and active.canUndo())
            self.actRedo.setEnabled(hasMdiChild and active.canRedo())
        except Exception as e: dumpException(e)



    def updateWindowMenu(self):
        self.windowMenu.clear()

        toolbar_nodes = self.windowMenu.addAction("工具面板")
        toolbar_nodes.setCheckable(True)
        toolbar_nodes.triggered.connect(self.onWindowNodesToolbar)
        toolbar_nodes.setChecked(self.toolPanelDock.isVisible())

        toolbar_simpleLogger = self.windowMenu.addAction("简单日志面板")
        toolbar_simpleLogger.setCheckable(True)
        toolbar_simpleLogger.triggered.connect(self.onWindowSimpleLoggerToolbar)
        toolbar_simpleLogger.setChecked(self.simpleLoggerDock.isVisible())

        self.windowMenu.addSeparator()

        self.windowMenu.addAction(self.actClose)
        self.windowMenu.addAction(self.actCloseAll)
        self.windowMenu.addSeparator()
        self.windowMenu.addAction(self.actTile)
        self.windowMenu.addAction(self.actCascade)
        self.windowMenu.addSeparator()
        self.windowMenu.addAction(self.actNext)
        self.windowMenu.addAction(self.actPrevious)
        self.windowMenu.addAction(self.actSeparator)

        windows = self.mdiArea.subWindowList()
        self.actSeparator.setVisible(len(windows) != 0)

        # for i, window in enumerate(windows):
        #     child = window.widget()

        #     text = "%d %s" % (i + 1, child.getUserFriendlyFilename())
        #     if i < 9:
        #         text = '&' + text

        #     action = self.windowMenu.addAction(text)
        #     action.setCheckable(True)
        #     action.setChecked(child is self.getCurrentNodeEditorWidget())
        #     action.triggered.connect(self.windowMapper.map)
        #     self.windowMapper.setMapping(action, window)

    def onWindowNodesToolbar(self):
        if self.toolPanelDock.isVisible():
            self.toolPanelDock.hide()
        else:
            self.toolPanelDock.show()

    def onWindowSimpleLoggerToolbar(self):
        if self.simpleLoggerDock.isVisible():
            self.simpleLoggerDock.hide()
        else:
            self.simpleLoggerDock.show()

    def createToolBars(self):
        pass

    def createToolPanelDock(self):
        self.toolPanel = QDMToolPanel()

        self.toolPanelDock = QDockWidget("工具面板")
        self.toolPanelDock.setWidget(self.toolPanel)
        self.toolPanelDock.setFloating(False)

        self.addDockWidget(Qt.RightDockWidgetArea, self.toolPanelDock)

    def createSimpleLoggerDock(self):
        self.simpleLoggerBrowser = SimpleLoggerBrowser()
        SimpleLogger.instance().newNotify.connect(self.simpleLoggerBrowser.updateNewMsg)
        
        self.simpleLoggerDock = QDockWidget(f"简单日志 - {logging.getLevelName(LEVEL)}")
        self.simpleLoggerDock.setWidget(self.simpleLoggerBrowser)
        self.simpleLoggerDock.setFloating(False)

        self.addDockWidget(Qt.BottomDockWidgetArea, self.simpleLoggerDock)


    def createStatusBar(self):
        self.statusBar().showMessage("Ready")

    def createMdiChild(self, child_widget=None):
        nodeeditor = child_widget if child_widget is not None else ConnSubWindow()
        subwnd = self.mdiArea.addSubWindow(nodeeditor)
        subwnd.setWindowIcon(self.empty_icon)
        # nodeeditor.scene.addItemSelectedListener(self.updateEditMenu)
        # nodeeditor.scene.addItemsDeselectedListener(self.updateEditMenu)
        nodeeditor.scene.history.addHistoryModifiedListener(self.updateEditMenu)
        nodeeditor.addCloseEventListener(self.onSubWndClose)
        return subwnd

    def onSubWndClose(self, widget, event):
        existing = self.findMdiChild(widget.filename)
        self.mdiArea.setActiveSubWindow(existing)

        if self.maybeSave():
            for edge in widget.scene.edges:
                try:
                    edge.remove()
                except Exception as e: 
                    easyError(e)

            for node in widget.scene.nodes:
                try:
                    node.remove()
                except Exception as e: 
                    easyError(e)

            event.accept()
        else:
            event.ignore()


    def findMdiChild(self, filename):
        for window in self.mdiArea.subWindowList():
            if window.widget().filename == filename:
                return window
        return None

    def readSettings(self):
        super().readSettings()
        settings = QSettings(self.name_company, self.name_product)
        GlobalSettingManager.instance().viewPortUpdateMode = settings.value("viewPortUpdateMode", GlobalSettingManager.instance().viewPortUpdateMode)
        GlobalSettingManager.instance().connectionType = settings.value("connectionType", GlobalSettingManager.instance().connectionType)

    def writeSettings(self):
        super().writeSettings()
        settings = QSettings(self.name_company, self.name_product)
        settings.setValue("viewPortUpdateMode", GlobalSettingManager.instance().viewPortUpdateMode)
        settings.setValue("connectionType", GlobalSettingManager.instance().connectionType)
