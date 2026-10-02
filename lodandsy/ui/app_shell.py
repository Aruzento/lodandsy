from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QWidget

from lodandsy.ui.inspector_panel import InspectorPanel
from lodandsy.ui.left_rail import LeftRail
from lodandsy.ui.right_rail import RightRail
from lodandsy.ui.tree_panel import TreePanel


class AppShell(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setObjectName("appShell")
        self.setWindowTitle("LODANDSY")
        self.resize(1280, 800)

        self.central_surface = QWidget(self)
        self.central_surface.setObjectName("centralSurface")
        self.setCentralWidget(self.central_surface)

        self.left_rail = LeftRail(self)
        self.right_rail = RightRail(self)

        self.addToolBar(
            Qt.ToolBarArea.LeftToolBarArea,
            self.left_rail,
        )
        self.addToolBar(
            Qt.ToolBarArea.RightToolBarArea,
            self.right_rail,
        )

        self.tree_panel = TreePanel(self)
        self.inspector_panel = InspectorPanel(self)

        self.addDockWidget(
            Qt.DockWidgetArea.LeftDockWidgetArea,
            self.tree_panel,
        )
        self.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea,
            self.inspector_panel,
        )

        self.left_rail.tree_action.toggled.connect(
            self.tree_panel.setVisible
        )
        self.tree_panel.visibilityChanged.connect(
            self.left_rail.tree_action.setChecked
        )

        self.right_rail.inspector_action.toggled.connect(
            self.inspector_panel.setVisible
        )
        self.inspector_panel.visibilityChanged.connect(
            self.right_rail.inspector_action.setChecked
        )