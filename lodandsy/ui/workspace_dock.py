from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDockWidget,
    QWidget,
)


class WorkspaceDock(QDockWidget):
    def __init__(
        self,
        key: str,
        title: str,
        content: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent)

        if not key:
            raise ValueError(
                "WorkspaceDock key must not be empty"
            )

        self.key = key

        self.setObjectName(
            f"workspaceDock:{key}"
        )

        self.setAllowedAreas(
            Qt.DockWidgetArea.AllDockWidgetAreas
        )

        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        self.setWidget(content)

        self._floating_controls_timer = QTimer(self)
        self._floating_controls_timer.setSingleShot(True)

        self._floating_controls_timer.timeout.connect(
            self._enable_floating_window_controls
        )

        self.topLevelChanged.connect(
            self._on_top_level_changed
        )

    def _on_top_level_changed(
        self,
        floating: bool,
    ) -> None:
        if not floating:
            self._floating_controls_timer.stop()
            return

        self._floating_controls_timer.start(0)

    def _enable_floating_window_controls(
        self,
    ) -> None:
        if not self.isFloating():
            return

        required_flags = (
            Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        current_flags = self.windowFlags()

        if (
            current_flags & required_flags
        ) == required_flags:
            return

        self.setWindowFlags(
            current_flags
            | required_flags
        )

        self.show()