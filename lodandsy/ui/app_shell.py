from PySide6.QtCore import (
    QPoint,
    QRect,
    QSize,
    Qt,
)
from PySide6.QtWidgets import QMainWindow, QWidget

from lodandsy.ui.fixed_panel_host import FixedPanelHost
from lodandsy.ui.inspector_panel import InspectorPanel
from lodandsy.ui.left_rail import LeftRail
from lodandsy.ui.right_rail import RightRail
from lodandsy.ui.tree_panel import TreePanel
from lodandsy.ui.workspace_dock import WorkspaceDock
from lodandsy.ui.workspace_drop_overlay import (
    WorkspaceDropOverlay,
)


class AppShell(QMainWindow):
    WORKSPACE_SIDE_DOCK_SIZE = 420
    WORKSPACE_TOP_BOTTOM_DOCK_SIZE = 280

    def __init__(self) -> None:
        super().__init__()

        self.setObjectName("appShell")
        self.setWindowTitle("LODANDSY")
        self.resize(1280, 800)

        self.setDockNestingEnabled(False)

        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
        )

        self.central_surface = QWidget(self)
        self.central_surface.setObjectName(
            "centralSurface"
        )

        self.setCentralWidget(
            self.central_surface
        )

        self._central_minimum_size = QSize(
            self.central_surface.minimumSize()
        )
        self._central_maximum_size = QSize(
            self.central_surface.maximumSize()
        )

        self.workspace_drop_overlay = (
            WorkspaceDropOverlay(self)
        )

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

        self.tree_host = FixedPanelHost(
            title="Tree Host",
            object_name="treeHost",
            area=Qt.ToolBarArea.LeftToolBarArea,
            panel=self.tree_panel,
            parent=self,
        )

        self.inspector_host = FixedPanelHost(
            title="Inspector Host",
            object_name="inspectorHost",
            area=Qt.ToolBarArea.RightToolBarArea,
            panel=self.inspector_panel,
            parent=self,
        )

        self.addToolBarBreak(
            Qt.ToolBarArea.LeftToolBarArea
        )
        self.addToolBar(
            Qt.ToolBarArea.LeftToolBarArea,
            self.tree_host,
        )

        self.addToolBarBreak(
            Qt.ToolBarArea.RightToolBarArea
        )
        self.addToolBar(
            Qt.ToolBarArea.RightToolBarArea,
            self.inspector_host,
        )

        self.left_rail.tree_action.toggled.connect(
            self.tree_host.setVisible
        )
        self.tree_host.visibilityChanged.connect(
            self.left_rail.tree_action.setChecked
        )

        self.right_rail.inspector_action.toggled.connect(
            self.inspector_host.setVisible
        )
        self.inspector_host.visibilityChanged.connect(
            self.right_rail.inspector_action.setChecked
        )

        self._workspace_docks: list[
            WorkspaceDock
        ] = []

        self._dragging_workspace_dock: (
            WorkspaceDock | None
        ) = None

        self._centered_workspace_dock: (
            WorkspaceDock | None
        ) = None

    def add_workspace_dock(
        self,
        dock: WorkspaceDock,
        area: Qt.DockWidgetArea = (
            Qt.DockWidgetArea.LeftDockWidgetArea
        ),
    ) -> None:
        self._leave_center_mode(
            dock
        )

        if dock not in self._workspace_docks:
            self._workspace_docks.append(
                dock
            )

            dock.interaction_settled.connect(
                self._on_workspace_dock_settled
            )

            dock.floating_drag_moved.connect(
                self._on_workspace_dock_drag_moved
            )

            dock.floating_drag_finished.connect(
                self._on_workspace_dock_drag_finished
            )

            dock.topLevelChanged.connect(
                self._on_workspace_top_level_changed
            )

            dock.visibilityChanged.connect(
                self._on_workspace_visibility_changed
            )

        dock.setAllowedAreas(
            Qt.DockWidgetArea.AllDockWidgetAreas
        )

        self.addDockWidget(
            area,
            dock,
        )

        dock.show()

        self._normalize_workspace_dock_size(
            dock
        )

    def remove_workspace_dock(
        self,
        dock: WorkspaceDock,
    ) -> None:
        self._leave_center_mode(
            dock
        )

        if dock in self._workspace_docks:
            self._workspace_docks.remove(
                dock
            )

        if self._dragging_workspace_dock is dock:
            self._clear_workspace_drop_overlay()

        self.removeDockWidget(
            dock
        )

        dock.hide()

    def workspace_docks(
        self,
    ) -> tuple[WorkspaceDock, ...]:
        return tuple(
            self._workspace_docks
        )

    def center_workspace_dock(
        self,
        dock: WorkspaceDock,
    ) -> None:
        if dock not in self._workspace_docks:
            self.add_workspace_dock(
                dock
            )

        current_center = (
            self._centered_workspace_dock
        )

        if (
            current_center is not None
            and current_center is not dock
        ):
            self._leave_center_mode(
                current_center
            )

        self._centered_workspace_dock = dock

        self._collapse_central_surface()

        dock.setAllowedAreas(
            Qt.DockWidgetArea.AllDockWidgetAreas
        )

        if dock.isFloating():
            dock.setFloating(False)

        self.addDockWidget(
            Qt.DockWidgetArea.LeftDockWidgetArea,
            dock,
        )

        dock.show()

        self.resizeDocks(
            [dock],
            [max(self.width(), 1)],
            Qt.Orientation.Horizontal,
        )

        dock.raise_()

    def is_workspace_dock_centered(
        self,
        dock: WorkspaceDock,
    ) -> bool:
        return (
            self._centered_workspace_dock
            is dock
        )

    def expand_workspace_dock(
        self,
        dock: WorkspaceDock,
    ) -> None:
        if dock.isFloating():
            dock.showMaximized()
            return

        self.center_workspace_dock(
            dock
        )

    def restore_workspace_dock_size(
        self,
        dock: WorkspaceDock,
    ) -> None:
        self._leave_center_mode(
            dock
        )

        self._normalize_workspace_dock_size(
            dock
        )

    def _on_workspace_dock_drag_moved(
        self,
        dock: object,
        global_position: object,
    ) -> None:
        if not isinstance(
            dock,
            WorkspaceDock,
        ):
            return

        if not isinstance(
            global_position,
            QPoint,
        ):
            return

        if not dock.isFloating():
            return

        self._dragging_workspace_dock = dock

        center_active = (
            self.workspace_drop_overlay
            .show_for_global_position(
                global_position,
                self._workspace_global_rect(),
            )
        )

        if center_active:
            dock.setAllowedAreas(
                Qt.DockWidgetArea.NoDockWidgetArea
            )
        else:
            dock.setAllowedAreas(
                Qt.DockWidgetArea.AllDockWidgetAreas
            )

    def _on_workspace_dock_drag_finished(
        self,
        dock: object,
        global_position: object,
    ) -> None:
        if not isinstance(
            dock,
            WorkspaceDock,
        ):
            return

        if not isinstance(
            global_position,
            QPoint,
        ):
            return

        center_drop = False

        if dock.isFloating():
            center_drop = (
                self.workspace_drop_overlay
                .show_for_global_position(
                    global_position,
                    self._workspace_global_rect(),
                )
            )

        dock.setAllowedAreas(
            Qt.DockWidgetArea.AllDockWidgetAreas
        )

        self._clear_workspace_drop_overlay()

        if center_drop:
            self.center_workspace_dock(
                dock
            )
            return

        self._normalize_workspace_dock_size(
            dock
        )

    def _on_workspace_dock_settled(
        self,
        dock: object,
    ) -> None:
        if not isinstance(
            dock,
            WorkspaceDock,
        ):
            return

        if not dock.isFloating():
            self._normalize_workspace_dock_size(
                dock
            )

    def _on_workspace_top_level_changed(
        self,
        floating: bool,
    ) -> None:
        dock = self.sender()

        if not isinstance(
            dock,
            WorkspaceDock,
        ):
            return

        if floating:
            self._leave_center_mode(
                dock
            )
            return

        if self._dragging_workspace_dock is dock:
            self._clear_workspace_drop_overlay()

    def _on_workspace_visibility_changed(
        self,
        visible: bool,
    ) -> None:
        dock = self.sender()

        if not isinstance(
            dock,
            WorkspaceDock,
        ):
            return

        if visible:
            return

        self._leave_center_mode(
            dock
        )

        if self._dragging_workspace_dock is dock:
            self._clear_workspace_drop_overlay()

    def _workspace_global_rect(self) -> QRect:
        top_left = (
            self.central_surface.mapToGlobal(
                QPoint(
                    0,
                    0,
                )
            )
        )

        return QRect(
            top_left,
            self.central_surface.size(),
        )

    def _collapse_central_surface(self) -> None:
        self.central_surface.setMinimumSize(
            0,
            0,
        )

        self.central_surface.setMaximumSize(
            0,
            0,
        )

    def _restore_central_surface(self) -> None:
        self.central_surface.setMinimumSize(
            self._central_minimum_size
        )

        self.central_surface.setMaximumSize(
            self._central_maximum_size
        )

        self.central_surface.show()

    def _clear_workspace_drop_overlay(
        self,
    ) -> None:
        dock = self._dragging_workspace_dock

        if dock is not None:
            dock.setAllowedAreas(
                Qt.DockWidgetArea.AllDockWidgetAreas
            )

        self._dragging_workspace_dock = None

        self.workspace_drop_overlay.hide_overlay()

    def _leave_center_mode(
        self,
        dock: WorkspaceDock,
    ) -> None:
        if (
            self._centered_workspace_dock
            is not dock
        ):
            return

        self._centered_workspace_dock = None

        self._restore_central_surface()

    def _normalize_workspace_dock_size(
        self,
        dock: WorkspaceDock,
    ) -> None:
        if dock.isFloating():
            return

        if self.is_workspace_dock_centered(
            dock
        ):
            return

        area = self.dockWidgetArea(
            dock
        )

        if area in (
            Qt.DockWidgetArea.LeftDockWidgetArea,
            Qt.DockWidgetArea.RightDockWidgetArea,
        ):
            self.resizeDocks(
                [dock],
                [self.WORKSPACE_SIDE_DOCK_SIZE],
                Qt.Orientation.Horizontal,
            )
            return

        if area in (
            Qt.DockWidgetArea.TopDockWidgetArea,
            Qt.DockWidgetArea.BottomDockWidgetArea,
        ):
            self.resizeDocks(
                [dock],
                [
                    self.WORKSPACE_TOP_BOTTOM_DOCK_SIZE
                ],
                Qt.Orientation.Vertical,
            )