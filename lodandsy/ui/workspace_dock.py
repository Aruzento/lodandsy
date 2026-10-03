from PySide6.QtCore import (
    QEvent,
    QPoint,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QCloseEvent,
    QCursor,
    QGuiApplication,
    QMouseEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QWidget,
)


class WorkspaceDock(QDockWidget):
    drag_started = Signal(
        object,
        object,
        object,
    )
    drag_moved = Signal(
        object,
        object,
    )
    drag_finished = Signal(
        object,
        object,
    )

    float_requested = Signal(object)
    closed = Signal(object)

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

        # Native Qt docking by dragging is intentionally
        # disabled. WorkspaceDock owns drag recognition,
        # AppShell owns placement.
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        self.setWidget(content)

        self._drag_active = False
        self._manual_drag = False

        self._drag_grab_offset = QPoint()

        self._docked_press_global: (
            QPoint | None
        ) = None
        self._docked_press_local: (
            QPoint | None
        ) = None

        self._native_press_global: (
            QPoint | None
        ) = None

        self._floating_controls_ready = False

        self._drag_tracking_timer = QTimer(self)
        self._drag_tracking_timer.setInterval(16)
        self._drag_tracking_timer.timeout.connect(
            self._track_drag
        )

        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(75)
        self._settle_timer.timeout.connect(
            self._settle_floating_window
        )

        self.topLevelChanged.connect(
            self._on_top_level_changed
        )

    def event(
        self,
        event: QEvent,
    ) -> bool:
        event_type = event.type()

        if (
            event_type
            == QEvent.Type.NonClientAreaMouseButtonPress
            and self.isFloating()
        ):
            self._native_press_global = (
                self._global_position(event)
            )

            return super().event(event)

        if (
            event_type
            == QEvent.Type.NonClientAreaMouseMove
            and self.isFloating()
        ):
            global_position = (
                self._global_position(event)
            )

            if (
                not self._drag_active
                and self._native_press_global
                is not None
                and self._drag_distance_reached(
                    self._native_press_global,
                    global_position,
                )
            ):
                self._begin_drag(
                    global_position=global_position,
                    grab_offset=QPoint(),
                    manual=False,
                )

            elif (
                self._drag_active
                and not self._manual_drag
            ):
                self._update_drag(
                    global_position
                )

            return super().event(event)

        if (
            event_type
            == QEvent.Type.NonClientAreaMouseButtonRelease
            and self.isFloating()
        ):
            result = super().event(event)

            global_position = (
                self._global_position(event)
            )

            self._native_press_global = None

            if (
                self._drag_active
                and not self._manual_drag
            ):
                self._finish_drag(
                    global_position
                )

            return result

        return super().event(event)

    def mousePressEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        if (
            not self.isFloating()
            and event.button()
            == Qt.MouseButton.LeftButton
            and self._is_docked_title_position(
                event.position().toPoint()
            )
        ):
            self._docked_press_global = (
                event.globalPosition().toPoint()
            )
            self._docked_press_local = (
                event.position().toPoint()
            )

            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        global_position = (
            event.globalPosition().toPoint()
        )

        if (
            self._drag_active
            and self._manual_drag
        ):
            self._update_drag(
                global_position
            )

            event.accept()
            return

        if (
            not self.isFloating()
            and self._docked_press_global
            is not None
            and self._docked_press_local
            is not None
            and (
                event.buttons()
                & Qt.MouseButton.LeftButton
            )
        ):
            if self._drag_distance_reached(
                self._docked_press_global,
                global_position,
            ):
                grab_offset = QPoint(
                    self._docked_press_local
                )

                self._docked_press_global = None
                self._docked_press_local = None

                self._begin_drag(
                    global_position=global_position,
                    grab_offset=grab_offset,
                    manual=True,
                )

            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        global_position = (
            event.globalPosition().toPoint()
        )

        if (
            self._drag_active
            and self._manual_drag
            and event.button()
            == Qt.MouseButton.LeftButton
        ):
            self._finish_drag(
                global_position
            )

            event.accept()
            return

        if (
            self._docked_press_global
            is not None
        ):
            self._clear_docked_press()

            event.accept()
            return

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        if (
            not self.isFloating()
            and event.button()
            == Qt.MouseButton.LeftButton
            and self._is_docked_title_position(
                event.position().toPoint()
            )
        ):
            self._clear_docked_press()

            self.float_requested.emit(
                self
            )

            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    def closeEvent(
        self,
        event: QCloseEvent,
    ) -> None:
        super().closeEvent(event)

        if not event.isAccepted():
            return

        self._cancel_drag()

        self.closed.emit(
            self
        )

    def _begin_drag(
        self,
        global_position: QPoint,
        grab_offset: QPoint,
        manual: bool,
    ) -> None:
        if self._drag_active:
            return

        self._drag_active = True
        self._manual_drag = manual
        self._drag_grab_offset = QPoint(
            grab_offset
        )

        self._drag_tracking_timer.start()

        self.drag_started.emit(
            self,
            global_position,
            QPoint(grab_offset),
        )

        self._update_drag(
            global_position
        )

    def _update_drag(
        self,
        global_position: QPoint,
    ) -> None:
        if not self._drag_active:
            return

        if (
            self._manual_drag
            and self.isFloating()
        ):
            self.move(
                global_position
                - self._drag_grab_offset
            )

        self.drag_moved.emit(
            self,
            global_position,
        )

    def _finish_drag(
        self,
        global_position: QPoint,
    ) -> None:
        if not self._drag_active:
            return

        self._drag_active = False
        self._manual_drag = False
        self._drag_grab_offset = QPoint()

        self._drag_tracking_timer.stop()

        self._clear_docked_press()
        self._native_press_global = None

        self.drag_finished.emit(
            self,
            global_position,
        )

        self._schedule_floating_settle()

    def _cancel_drag(self) -> None:
        self._drag_active = False
        self._manual_drag = False
        self._drag_grab_offset = QPoint()

        self._drag_tracking_timer.stop()

        self._clear_docked_press()
        self._native_press_global = None

    def _track_drag(self) -> None:
        if not self._drag_active:
            self._drag_tracking_timer.stop()
            return

        global_position = QCursor.pos()

        if self._manual_drag:
            if not (
                QGuiApplication.mouseButtons()
                & Qt.MouseButton.LeftButton
            ):
                self._finish_drag(
                    global_position
                )
                return

        self._update_drag(
            global_position
        )

    def _clear_docked_press(self) -> None:
        self._docked_press_global = None
        self._docked_press_local = None

    def _is_docked_title_position(
        self,
        position: QPoint,
    ) -> bool:
        content = self.widget()

        if content is None:
            return False

        content_geometry = content.geometry()

        if (
            self.features()
            & QDockWidget.DockWidgetFeature.DockWidgetVerticalTitleBar
        ):
            return (
                position.x()
                < content_geometry.left()
            )

        return (
            position.y()
            < content_geometry.top()
        )

    @staticmethod
    def _drag_distance_reached(
        start: QPoint,
        current: QPoint,
    ) -> bool:
        distance = (
            start
            - current
        ).manhattanLength()

        return (
            distance
            >= QApplication.startDragDistance()
        )

    def _on_top_level_changed(
        self,
        floating: bool,
    ) -> None:
        if not floating:
            self._floating_controls_ready = False
            self._native_press_global = None
            return

        self._schedule_floating_settle()

    def _schedule_floating_settle(self) -> None:
        self._settle_timer.start()

    def _settle_floating_window(self) -> None:
        if not self.isFloating():
            return

        if self._drag_active:
            self._schedule_floating_settle()
            return

        if (
            QGuiApplication.mouseButtons()
            != Qt.MouseButton.NoButton
        ):
            self._schedule_floating_settle()
            return

        self._enable_floating_window_controls()

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