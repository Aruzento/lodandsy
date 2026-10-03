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
from lodandsy.ui.workspace_placement import (
    WorkspacePlacement,
)


class AppShell(QMainWindow):
    WORKSPACE_SIDE_DOCK_SIZE = 420
    WORKSPACE_TOP_BOTTOM_DOCK_SIZE = 280

    def __init__(self) -> None:
        super().__init__()

        self.setObjectName("appShell")
        self.setWindowTitle("LODANDSY")
        self.resize(1280, 800)

        # WorkspaceDock может образовывать несколько
        # рядов/колонок. Сам drag при этом остаётся нашим:
        # DockWidgetMovable у WorkspaceDock отключён.
        self.setDockNestingEnabled(True)

        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowNestedDocks
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

        self._centered_workspace_docks: set[
            WorkspaceDock
        ] = set()

        self._workspace_drop_rect: (
            QRect | None
        ) = None

        self._active_workspace_drop_zone: (
            WorkspacePlacement | None
        ) = None

        self._pending_workspace_placement: (
            tuple[
                WorkspaceDock,
                WorkspacePlacement,
            ]
            | None
        ) = None

        self._workspace_drop_timer = QTimer(self)
        self._workspace_drop_timer.setSingleShot(
            True
        )
        self._workspace_drop_timer.timeout.connect(
            self._apply_pending_workspace_placement
        )

    def add_workspace_dock(
        self,
        dock: WorkspaceDock,
        placement: WorkspacePlacement = (
            WorkspacePlacement.LEFT
        ),
    ) -> None:
        self._register_workspace_dock(
            dock
        )

        self.place_workspace_dock(
            dock,
            placement,
        )

    def place_workspace_dock(
        self,
        dock: WorkspaceDock,
        placement: WorkspacePlacement,
        global_position: QPoint | None = None,
        grab_offset: QPoint | None = None,
    ) -> None:
        self._register_workspace_dock(
            dock
        )

        dock.setAllowedAreas(
            Qt.DockWidgetArea.AllDockWidgetAreas
        )

        if placement == WorkspacePlacement.FLOATING:
            self._leave_center_mode(
                dock
            )

            if (
                self.dockWidgetArea(dock)
                == Qt.DockWidgetArea.NoDockWidgetArea
                and not dock.isFloating()
            ):
                self.addDockWidget(
                    Qt.DockWidgetArea.LeftDockWidgetArea,
                    dock,
                )

            if not dock.isFloating():
                dock.setFloating(True)

            if (
                global_position is not None
                and grab_offset is not None
            ):
                dock.move(
                    global_position
                    - grab_offset
                )

            dock.show()
            dock.raise_()

            return

        if placement == WorkspacePlacement.CENTER:
            self._place_workspace_in_center(
                dock
            )
            return

        self._leave_center_mode(
            dock
        )

        area = self._dock_area_for_placement(
            placement
        )

        if area is None:
            raise ValueError(
                f"Unsupported workspace placement: "
                f"{placement}"
            )

        self._place_workspace_at_edge(
            dock,
            placement,
            area,
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
            self._clear_workspace_drag_state()

        if (
            self._pending_workspace_placement
            is not None
            and self._pending_workspace_placement[0]
            is dock
        ):
            self._pending_workspace_placement = None
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

    def is_workspace_dock_centered(
        self,
        dock: WorkspaceDock,
    ) -> bool:
        return (
            dock
            in self._centered_workspace_docks
        )

    def _register_workspace_dock(
        self,
        dock: WorkspaceDock,
    ) -> None:
        if dock in self._workspace_docks:
            return

        self._workspace_docks.append(
            dock
        )

        dock.drag_started.connect(
            self._on_workspace_drag_started
        )

        dock.drag_moved.connect(
            self._on_workspace_drag_moved
        )

        dock.drag_finished.connect(
            self._on_workspace_drag_finished
        )

        dock.float_requested.connect(
            self._on_workspace_float_requested
        )

        dock.topLevelChanged.connect(
            self._on_workspace_top_level_changed
        )

        dock.closed.connect(
            self._on_workspace_dock_closed
        )

    def _on_workspace_drag_started(
        self,
        dock: object,
        global_position: object,
        grab_offset: object,
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

        if not isinstance(
            grab_offset,
            QPoint,
        ):
            return

        was_floating = dock.isFloating()

        self._dragging_workspace_dock = dock
        self._workspace_drop_rect = None
        self._active_workspace_drop_zone = None

        self.place_workspace_dock(
            dock,
            WorkspacePlacement.FLOATING,
            (
                None
                if was_floating
                else global_position
            ),
            (
                None
                if was_floating
                else grab_offset
            ),
        )

        dock.setAllowedAreas(
            Qt.DockWidgetArea.NoDockWidgetArea
        )

        self._update_workspace_drop_target(
            dock,
            global_position,
        )

    def _on_workspace_drag_moved(
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

        if (
            self._dragging_workspace_dock
            is not dock
        ):
            return

        self._update_workspace_drop_target(
            dock,
            global_position,
        )

    def _on_workspace_drag_finished(
        self,
        dock: object,
        _global_position: object,
    ) -> None:
        if not isinstance(
            dock,
            WorkspaceDock,
        ):
            return

        if (
            self._dragging_workspace_dock
            is not dock
        ):
            return

        placement = (
            self._active_workspace_drop_zone
            or WorkspacePlacement.FLOATING
        )

        self._pending_workspace_placement = (
            dock,
            placement,
        )

        self._clear_workspace_drag_state()

        self._workspace_drop_timer.start(0)

    def _on_workspace_float_requested(
        self,
        dock: object,
    ) -> None:
        if not isinstance(
            dock,
            WorkspaceDock,
        ):
            return

        self.place_workspace_dock(
            dock,
            WorkspacePlacement.FLOATING,
        )

    def _apply_pending_workspace_placement(
        self,
    ) -> None:
        pending = (
            self._pending_workspace_placement
        )

        self._pending_workspace_placement = None

        if pending is None:
            return

        dock, placement = pending

        if dock not in self._workspace_docks:
            return

        self.place_workspace_dock(
            dock,
            placement,
        )

    def _update_workspace_drop_target(
        self,
        dock: WorkspaceDock,
        global_position: QPoint,
    ) -> None:
        if not dock.isFloating():
            return

        workspace_rect = (
            self._workspace_drop_rect_for_drag()
        )

        self._active_workspace_drop_zone = (
            self.workspace_drop_overlay
            .show_for_global_position(
                global_position,
                workspace_rect,
            )
        )

    def _place_workspace_at_edge(
        self,
        dock: WorkspaceDock,
        placement: WorkspacePlacement,
        area: Qt.DockWidgetArea,
    ) -> None:
        # Ищем окно, которое сейчас находится ближе
        # всего к свободной central_surface с нужной стороны.
        #
        # Новый dock должен вставиться между этим anchor
        # и свободным workspace — именно там нарисован preview.
        anchor = self._inner_workspace_anchor(
            area,
            exclude=dock,
        )

        # Сначала оба QDockWidget должны принадлежать
        # layout QMainWindow.
        self._dock_workspace_in_area(
            dock,
            area,
        )

        if anchor is not None:
            if placement in (
                WorkspacePlacement.LEFT,
                WorkspacePlacement.RIGHT,
            ):
                orientation = (
                    Qt.Orientation.Horizontal
                )
            else:
                orientation = (
                    Qt.Orientation.Vertical
                )

            if placement in (
                WorkspacePlacement.LEFT,
                WorkspacePlacement.TOP,
            ):
                # LEFT:
                # anchor | new | central
                #
                # TOP:
                # anchor
                # new
                # central
                self.splitDockWidget(
                    anchor,
                    dock,
                    orientation,
                )
            else:
                # RIGHT:
                # central | new | anchor
                #
                # BOTTOM:
                # central
                # new
                # anchor
                self.splitDockWidget(
                    dock,
                    anchor,
                    orientation,
                )

            dock.show()
            dock.raise_()

        self._normalize_workspace_dock_size(
            dock
        )

    def _inner_workspace_anchor(
        self,
        area: Qt.DockWidgetArea,
        exclude: WorkspaceDock,
    ) -> WorkspaceDock | None:
        candidates = [
            current
            for current in self._workspace_docks
            if (
                current is not exclude
                and not current.isFloating()
                and not current.isHidden()
                and (
                    current
                    not in self._centered_workspace_docks
                )
                and self.dockWidgetArea(
                    current
                )
                == area
            )
        ]

        if not candidates:
            return None

        if area == Qt.DockWidgetArea.LeftDockWidgetArea:
            return max(
                candidates,
                key=lambda current: (
                    current.geometry().right()
                ),
            )

        if area == Qt.DockWidgetArea.RightDockWidgetArea:
            return min(
                candidates,
                key=lambda current: (
                    current.geometry().left()
                ),
            )

        if area == Qt.DockWidgetArea.TopDockWidgetArea:
            return max(
                candidates,
                key=lambda current: (
                    current.geometry().bottom()
                ),
            )

        if area == Qt.DockWidgetArea.BottomDockWidgetArea:
            return min(
                candidates,
                key=lambda current: (
                    current.geometry().top()
                ),
            )

        return None

    def _place_workspace_in_center(
        self,
        dock: WorkspaceDock,
    ) -> None:
        anchor = next(
            (
                current
                for current
                in self._centered_workspace_docks
                if current is not dock
            ),
            None,
        )

        self._centered_workspace_docks.add(
            dock
        )

        self._collapse_central_surface()

        self._dock_workspace_in_area(
            dock,
            Qt.DockWidgetArea.LeftDockWidgetArea,
        )

        if anchor is not None:
            self.tabifyDockWidget(
                anchor,
                dock,
            )

        self.resizeDocks(
            [dock],
            [max(self.width(), 1)],
            Qt.Orientation.Horizontal,
        )

        dock.show()
        dock.raise_()

    def _dock_workspace_in_area(
        self,
        dock: WorkspaceDock,
        area: Qt.DockWidgetArea,
    ) -> None:
        dock.setAllowedAreas(
            Qt.DockWidgetArea.AllDockWidgetAreas
        )

        if dock.isFloating():
            dock.setDockLocation(
                area
            )
            dock.setFloating(False)

        elif (
            self.dockWidgetArea(dock)
            == Qt.DockWidgetArea.NoDockWidgetArea
        ):
            self.addDockWidget(
                area,
                dock,
            )

        else:
            dock.setDockLocation(
                area
            )

        dock.show()
        dock.raise_()

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

        if not floating:
            return

        if (
            self._dragging_workspace_dock
            is dock
        ):
            return

        self._leave_center_mode(
            dock
        )

        dock.setAllowedAreas(
            Qt.DockWidgetArea.AllDockWidgetAreas
        )

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
            self._clear_workspace_drag_state()

        if (
            self._pending_workspace_placement
            is not None
            and self._pending_workspace_placement[0]
            is dock
        ):
            self._pending_workspace_placement = None
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

    def _clear_workspace_drag_state(
        self,
    ) -> None:
        self._dragging_workspace_dock = None
        self._workspace_drop_rect = None
        self._active_workspace_drop_zone = None

        self.workspace_drop_overlay.hide_overlay()

    def _leave_center_mode(
        self,
        dock: WorkspaceDock,
    ) -> None:
        self._centered_workspace_docks.discard(
            dock
        )

        if self._centered_workspace_docks:
            return

        self._restore_central_surface()

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

    def _normalize_workspace_dock_size(
        self,
        dock: WorkspaceDock,
    ) -> None:
        if dock.isFloating():
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

    @staticmethod
    def _dock_area_for_placement(
        placement: WorkspacePlacement,
    ) -> Qt.DockWidgetArea | None:
        area_map = {
            WorkspacePlacement.LEFT: (
                Qt.DockWidgetArea.LeftDockWidgetArea
            ),
            WorkspacePlacement.TOP: (
                Qt.DockWidgetArea.TopDockWidgetArea
            ),
            WorkspacePlacement.RIGHT: (
                Qt.DockWidgetArea.RightDockWidgetArea
            ),
            WorkspacePlacement.BOTTOM: (
                Qt.DockWidgetArea.BottomDockWidgetArea
            ),
        }

        return area_map.get(
            placement
        )