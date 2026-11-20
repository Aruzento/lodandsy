from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QToolBar, QToolButton, QWidget

from lodandsy.ui.icons import icon


class RightRail(QToolBar):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Right Rail", parent)

        self.setObjectName("rightRail")
        self.setFixedWidth(36)
        self.setMovable(False)
        self.setFloatable(False)
        self.setAllowedAreas(Qt.ToolBarArea.RightToolBarArea)

        self.inspector_action = QAction("Inspector", self)
        self.inspector_action.setIcon(icon("inspector"))
        self.inspector_action.setToolTip("Показать / скрыть Inspector")
        self.inspector_action.setCheckable(True)
        self.inspector_action.setChecked(True)

        self.addAction(self.inspector_action)

        self.settings_button = QToolButton(self)
        self.settings_button.setIcon(icon("settings"))
        self.settings_button.setToolTip("Настройки проекта")
        self.settings_button.setAccessibleName("Настройки проекта")
        self.settings_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.settings_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.settings_menu = QMenu(self.settings_button)
        self.settings_button.setMenu(self.settings_menu)
        self.addWidget(self.settings_button)
