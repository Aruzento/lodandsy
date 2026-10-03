from PySide6.QtCore import (
    QPoint,
    QRect,
    QSize,
    Qt,
    QTimer,
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

        self._workspace_drop_rect: (
            QRect | None
        ) = None

        self._active_workspace_drop_zone: (
            str | None
        ) = None

        self._pending_workspace_drop: (
            tuple[WorkspaceDock, str] | None
        ) = None

        self._workspace_drop_timer = QTimer(self)
        self._workspace_drop_timer.setSingleShot(
            True
        )
        self._workspace_drop_timer.timeout.connect(
            self._apply_pending_workspace_drop
        )

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

            dock.closed.connect(
                self._on_workspace_dock_closed
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

        if (
            self._pending_workspace_drop
            is not None
            and self._pending_workspace_drop[0]
            is dock
        ):
            self._pending_workspace_drop = None
            self._workspace_drop_timer.stop()

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

        dock.set_center_drop_active(
            False
        )

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

        workspace_rect = (
            self._workspace_drop_rect_for_drag()
        )

        inside_workspace = (
            workspace_rect.contains(
                global_position
            )
        )

        active_zone = (
            self.workspace_drop_overlay
            .show_for_global_position(
                global_position,
                workspace_rect,
            )
        )

        self._active_workspace_drop_zone = (
            active_zone
        )

        dock.set_center_drop_active(
            active_zone is not None
        )

        if inside_workspace:
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
        _global_position: object,
        custom_drop: bool,
    ) -> None:
        if not isinstance(
            dock,
            WorkspaceDock,
        ):
            return

        drop_zone = (
            self._active_workspace_drop_zone
        )

        dock.setCenterDropActive = None
        dock.set_center_drop_active(
            False
        )

        self._clear_workspace_drop_overlay()

        if (
            custom_drop
            and drop_zone is not None
        ):
            self._pending_workspace_drop = (
                dock,
                drop_zone,
            )

            self._workspace_drop_timer.start(0)
            return

        dock.setAllowedAreas(
            Qt.DockWidgetArea.AllDockWidgetAreas
        )

        self._normalize_workspace_dock_size(
            dock
        )

    def _apply_pending_workspace_drop(
        self,
    ) -> None:
        pending = self._pending_workspace_drop

        self._pending_workspace_drop = None

        if pending is None:
            return

        dock, drop_zone = pending

        if dock not in self._workspace_docks:
            return

        if (
            drop_zone
            == WorkspaceDropOverlay.ZONE_CENTER
        ):
            self.center_workspace_dock(
                dock
            )
            return

        self._dock_workspace_to_zone(
            dock,
            drop_zone,
        )

    def _dock_workspace_to_zone(
        self,
        dock: WorkspaceDock,
        drop_zone: str,
    ) -> None:
        area_map = {
            WorkspaceDropOverlay.ZONE_LEFT: (
                Qt.DockWidgetArea.LeftDockWidgetArea
            ),
            WorkspaceDropOverlay.ZONE_TOP: (
                Qt.DockWidgetArea.TopDockWidgetArea
            ),
            WorkspaceDropOverlay.ZONE_RIGHT: (
                Qt.DockWidgetArea.RightDockWidgetArea
            ),
            WorkspaceDropOverlay.ZONE_BOTTOM: (
                Qt.DockWidgetArea.BottomDockWidgetArea
            ),
        }

        area = area_map.get(
            drop_zone
        )

        if area is None:
            return

        dock.setAllowedAreas(
            Qt.DockWidgetArea.AllDockWidgetAreas
        )

        if dock.isFloating():
            dock.setFloating(False)

        self.addDockWidget(
            area,
            dock,
        )

        dock.show()

        self._normalize_workspace_dock_size(
            dock
        )

        dock.raise_()

    def _on_workspace_dock_settled(
        self,
        dock: object,
    ) -> None:
        if not isinstance(
            dock,
            WorkspaceDock,
        ):
            return

        if dock.isFloating():
            return

        if self.is_workspace_dock_centered(
            dock
        ):
            return

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

            self._workspace_drop_rect = None
            self._active_workspace_drop_zone = None

            return

        if self._dragging_workspace_dock is dock:
            self._clear_workspace_drop_overlay()

    def _on_workspace_dock_closed(
        self,
        dock: object,
    ) -> None:
        if not isinstance(
            dock,
            WorkspaceDock,
        ):
            return

        self._leave_center_mode(
            dock
        )

        if self._dragging_workspace_dock is dock:
            self._clear_workspace_drop_overlay()

        if (
            self._pending_workspace_drop
            is not None
            and self._pending_workspace_drop[0]
            is dock
        ):
            self._pending_workspace_drop = None
            self._workspace_drop_timer.stop()

    def _workspace_global_rect(
        self,
    ) -> QRect:
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

    def _workspace_drop_rect_for_drag(
        self,
    ) -> QRect:
        current_rect = (
            self._workspace_global_rect()
        )

        current_area = (
            current_rect.width()
            * current_rect.height()
        )

        stored_rect = (
            self._workspace_drop_rect
        )

        if stored_rect is None:
            self._workspace_drop_rect = QRect(
                current_rect
            )

            return QRect(
                current_rect
            )

        stored_area = (
            stored_rect.width()
            * stored_rect.height()
        )

        if current_area > stored_area:
            self._workspace_drop_rect = QRect(
                current_rect
            )

        return QRect(
            self._workspace_drop_rect
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
            dock.set_center_drop_active(
                False
            )
            dock.setAllowedAreas(
                Qt.DockWidgetArea.AllDockWidgetAreas
            )

        self._dragging_workspace_dock = None
        self._workspace_drop_rect = None
        self._active_workspace_drop_zone = None

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