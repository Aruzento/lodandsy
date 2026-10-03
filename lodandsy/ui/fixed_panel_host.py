from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QToolBar,
    QWidget,
)


class FixedPanelHost(QToolBar):
    def __init__(
        self,
        title: str,
        object_name: str,
        area: Qt.ToolBarArea,
        panel: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent)

        self.setObjectName(object_name)

        self.setMovable(False)
        self.setFloatable(False)
        self.setAllowedAreas(area)

        self.panel = panel
        self.panel_action = self.addWidget(
            panel
        )
        