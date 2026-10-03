from PySide6.QtCore import (
    QEvent,
    QPoint,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QCursor,
    QGuiApplication,
    QMouseEvent,
    QMoveEvent,
)
from PySide6.QtWidgets import (
    QDockWidget,
    QWidget,
)


class WorkspaceDock(QDockWidget):
    interaction_settled = Signal(object)

    floating_drag_moved = Signal(
        object,
        object,
    )
    floating_drag_finished = Signal(
        object,
        object,
    )

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

        self._floating_controls_ready = False
        self._native_title_drag_active = False

        self._settle_timer = QTimer(self)
        self._settle_timer.setInterval(75)

        self._settle_timer.timeout.connect(
            self._finish_interaction_if_possible
        )

        self.topLevelChanged.connect(
            self._on_top_level_changed
        )

        self.dockLocationChanged.connect(
            self._on_dock_location_changed
        )

    def event(
        self,
        event: QEvent,
    ) -> bool:
        event_type = event.type()

        result = super().event(event)

        if (
            event_type
            == QEvent.Type.NonClientAreaMouseButtonPress
            and self.isFloating()
        ):
            self._native_title_drag_active = True

        elif (
            event_type
            == QEvent.Type.NonClientAreaMouseMove
            and self.isFloating()
        ):
            self._native_title_drag_active = True

            self.floating_drag_moved.emit(
                self,
                self._global_position(event),
            )

            self._schedule_settle_check()

        elif (
            event_type
            == QEvent.Type.NonClientAreaMouseButtonRelease
            and self._native_title_drag_active
        ):
            global_position = (
                self._global_position(event)
            )

            self._native_title_drag_active = False

            self.floating_drag_finished.emit(
                self,
                global_position,
            )

            self._schedule_settle_check()

        return result

    def moveEvent(
        self,
        event: QMoveEvent,
    ) -> None:
        super().moveEvent(event)

        if not self.isFloating():
            return

        if not self._native_title_drag_active:
            return

        self.floating_drag_moved.emit(
            self,
            QCursor.pos(),
        )

        self._schedule_settle_check()

    def _on_top_level_changed(
        self,
        floating: bool,
    ) -> None:
        if not floating:
            self._native_title_drag_active = False
            self._floating_controls_ready = False

        self._schedule_settle_check()

    def _on_dock_location_changed(
        self,
        _area: Qt.DockWidgetArea,
    ) -> None:
        self._schedule_settle_check()

    def _schedule_settle_check(self) -> None:
        if self._settle_timer.isActive():
            return

        self._settle_timer.start()

    def _finish_interaction_if_possible(
        self,
    ) -> None:
        if self._native_title_drag_active:
            return

        if (
            QGuiApplication.mouseButtons()
            != Qt.MouseButton.NoButton
        ):
            return

        self._settle_timer.stop()

        if self.isFloating():
            self._enable_floating_window_controls()

        self.interaction_settled.emit(
            self
        )

    def _enable_floating_window_controls(
        self,
    ) -> None:
        if self._floating_controls_ready:
            return

        geometry = self.geometry()

        floating_flags = (
            Qt.WindowType.Window
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        self._floating_controls_ready = True

        self.setWindowFlags(
            floating_flags
        )

        self.setGeometry(
            geometry
        )

        self.show()
        self.raise_()
        self.activateWindow()

    @staticmethod
    def _global_position(
        event: QEvent,
    ) -> QPoint:
        if isinstance(
            event,
            QMouseEvent,
        ):
            return (
                event.globalPosition()
                .toPoint()
            )

        return QCursor.pos()