from collections.abc import Callable

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow

from lodandsy.ui.fixed_panel_host import FixedPanelHost
from lodandsy.ui.inspector_panel import InspectorPanel
from lodandsy.ui.left_rail import LeftRail
from lodandsy.ui.right_rail import RightRail
from lodandsy.ui.tree_panel import TreePanel
from lodandsy.ui.workspace_host import WorkspaceHost


class AppShell(QMainWindow):
    def __init__(self):
        super().__init__()
        self.close_guard: Callable[[], bool] | None = None
        self.setObjectName("appShell")
        self.setWindowTitle("LODANDSY")
        self.resize(1440, 960)
        self.left_rail = LeftRail(self)
        self.right_rail = RightRail(self)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self.left_rail)
        self.addToolBar(Qt.ToolBarArea.RightToolBarArea, self.right_rail)
        self.tree_panel = TreePanel(self)
        self.inspector_panel = InspectorPanel(self)
        self.tree_host = FixedPanelHost(
            title="Tree Host",
            object_name="treeHost",
            area=Qt.DockWidgetArea.LeftDockWidgetArea,
            panel=self.tree_panel,
            parent=self,
        )
        self.inspector_host = FixedPanelHost(
            title="Inspector Host",
            object_name="inspectorHost",
            area=Qt.DockWidgetArea.RightDockWidgetArea,
            panel=self.inspector_panel,
            parent=self,
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.tree_host)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.inspector_host)
        self.resizeDocks(
            [self.tree_host, self.inspector_host], [224, 244], Qt.Orientation.Horizontal
        )
        self.left_rail.tree_action.toggled.connect(self.tree_host.setVisible)
        self.tree_host.visibilityChanged.connect(self.left_rail.tree_action.setChecked)
        self.right_rail.inspector_action.toggled.connect(self.inspector_host.setVisible)
        self.inspector_host.visibilityChanged.connect(self.right_rail.inspector_action.setChecked)
        self.workspace = WorkspaceHost(self)

    def panel_widths(self):
        return {
            "tree": self.tree_host.width()
            if self.tree_host.isVisible()
            else self.tree_host.last_width,
            "inspector": self.inspector_host.width()
            if self.inspector_host.isVisible()
            else self.inspector_host.last_width,
        }

    def restore_panel_widths(self, values):
        for key, host in [("tree", self.tree_host), ("inspector", self.inspector_host)]:
            width = values.get(key)
            if type(width) is int:
                host.last_width = max(180, min(width, max(180, int(self.width() * 0.45))))
                if host.isVisible():
                    self.resizeDocks([host], [host.last_width], Qt.Orientation.Horizontal)

    @Slot(str)
    def show_notice(self, text):
        self.statusBar().showMessage(text, 5000)

    def closeEvent(self, event: QCloseEvent):
        if self.close_guard is not None and not self.close_guard():
            event.ignore()
            return
        super().closeEvent(event)
