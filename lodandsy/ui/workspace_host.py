from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
)

from lodandsy.ui.workspace_dock import WorkspaceDock


class WorkspaceHost(QMainWindow):
    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.setObjectName("workspaceHost")

        # QMainWindow создаётся как top-level window.
        # Здесь он используется как встроенный host.
        self.setWindowFlags(
            Qt.WindowType.Widget
        )

        self.setDockNestingEnabled(False)

        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.ForceTabbedDocks
        )

        placeholder = QWidget(self)
        placeholder.setObjectName(
            "workspacePlaceholder"
        )
        placeholder.setFixedSize(0, 0)

        self.setCentralWidget(
            placeholder
        )

        self._workspace_docks: list[
            WorkspaceDock
        ] = []

    def add_workspace_dock(
        self,
        dock: WorkspaceDock,
        area: Qt.DockWidgetArea = (
            Qt.DockWidgetArea.LeftDockWidgetArea
        ),
    ) -> None:
        same_area_docks = [
            current
            for current in self._workspace_docks
            if (
                not current.isFloating()
                and self.dockWidgetArea(current)
                == area
            )
        ]

        self.addDockWidget(
            area,
            dock,
        )

        if dock not in self._workspace_docks:
            self._workspace_docks.append(
                dock
            )

        if same_area_docks:
            self.tabifyDockWidget(
                same_area_docks[0],
                dock,
            )

        dock.show()
        dock.raise_()

    def remove_workspace_dock(
        self,
        dock: WorkspaceDock,
    ) -> None:
        if dock not in self._workspace_docks:
            return

        self.removeDockWidget(
            dock
        )

        self._workspace_docks.remove(
            dock
        )

    def workspace_docks(
        self,
    ) -> tuple[WorkspaceDock, ...]:
        return tuple(
            self._workspace_docks
        )