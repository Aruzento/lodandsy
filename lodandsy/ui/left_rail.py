from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QToolBar, QWidget


class LeftRail(QToolBar):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Left Rail", parent)

        self.setObjectName("leftRail")
        self.setMovable(False)
        self.setFloatable(False)
        self.setAllowedAreas(Qt.ToolBarArea.LeftToolBarArea)

        self.tree_action = QAction("Tree", self)
        self.tree_action.setCheckable(True)
        self.tree_action.setChecked(True)

        self.addAction(self.tree_action)