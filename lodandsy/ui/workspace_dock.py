from PySide6.QtCore import (
    QEvent,
    QPoint,
    QSize,
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
    QHBoxLayout,
    QLabel,
    QToolButton,
    QWidget,
)


class WorkspaceTitleBar(QWidget):
    drag_started = Signal(
        object,
        object,
    )
    drag_moved = Signal(object)
    drag_finished = Signal(object)

    float_requested = Signal()
    minimize_requested = Signal()
    maximize_restore_requested = Signal()
    close_requested = Signal()

    HEIGHT = 30

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.setObjectName(
            "workspaceTitleBar"
        )

        self.setFixedHeight(
            self.HEIGHT
        )

        self.title_label = QLabel(
            self
        )
        self.title_label.setObjectName(
            "workspaceTitle"
        )

        self.title_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )

        self.float_button = self._make_button(
            "workspaceFloatButton",
            "↗",
            "Float",
        )

        self.minimize_button = self._make_button(
            "workspaceMinimizeButton",
            "—",
            "Minimize",
        )

        self.maximize_button = self._make_button(
            "workspaceMaximizeButton",
            "□",
            "Maximize",
        )

        self.close_button = self._make_button(
            "workspaceCloseButton",
            "×",
            "Close",
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            8,
            0,
            2,
            0,
        )
        layout.setSpacing(2)

        layout.addWidget(
            self.title_label,
            1,
        )

        layout.addWidget(
            self.float_button
        )
        layout.addWidget(
            self.minimize_button
        )
        layout.addWidget(
            self.maximize_button
        )
        layout.addWidget(
            self.close_button
        )

        self.float_button.clicked.connect(
            self.float_requested
        )
        self.minimize_button.clicked.connect(
            self.minimize_requested
        )
        self.maximize_button.clicked.connect(
            self.maximize_restore_requested
        )
        self.close_button.clicked.connect(
            self.close_requested
        )

        self._press_global: QPoint | None = None
        self._press_dock_offset: QPoint | None = None
        self._drag_active = False

        self._tracking_timer = QTimer(self)
        self._tracking_timer.setInterval(16)
        self._tracking_timer.timeout.connect(
            self._track_pointer
        )

        self.set_floating(
            False
        )

    @property
    def drag_active(self) -> bool:
        return self._drag_active

    def sizeHint(self) -> QSize:
        return QSize(
            240,
            self.HEIGHT,
        )

    def minimumSizeHint(self) -> QSize:
        return QSize(
            100,
            self.HEIGHT,
        )

    def set_title(
        self,
        title: str,
    ) -> None:
        self.title_label.setText(
            title
        )

    def set_floating(
        self,
        floating: bool,
    ) -> None:
        self.float_button.setVisible(
            not floating
        )

        self.minimize_button.setVisible(
            floating
        )

        self.maximize_button.setVisible(
            floating
        )

        if not floating:
            self.set_maximized(
                False
            )

    def set_maximized(
        self,
        maximized: bool,
    ) -> None:
        if maximized:
            self.maximize_button.setText(
                "❐"
            )
            self.maximize_button.setToolTip(
                "Restore"
            )
            return

        self.maximize_button.setText(
            "□"
        )
        self.maximize_button.setToolTip(
            "Maximize"
        )

    def mousePressEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        if (
            event.button()
            != Qt.MouseButton.LeftButton
        ):
            super().mousePressEvent(
                event
            )
            return

        global_position = (
            event.globalPosition().toPoint()
        )

        dock = self.parentWidget()

        if dock is None:
            super().mousePressEvent(
                event
            )
            return

        self._press_global = QPoint(
            global_position
        )

        self._press_dock_offset = (
            dock.mapFromGlobal(
                global_position
            )
        )

        self._drag_active = False

        self._tracking_timer.start()

        event.accept()

    def mouseMoveEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        if self._press_global is None:
            super().mouseMoveEvent(
                event
            )
            return

        if not (
            event.buttons()
            & Qt.MouseButton.LeftButton
        ):
            self._finish_or_cancel(
                event.globalPosition().toPoint()
            )
            event.accept()
            return

        self._advance_drag(
            event.globalPosition().toPoint()
        )

        event.accept()

    def mouseReleaseEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        if (
            event.button()
            == Qt.MouseButton.LeftButton
            and self._press_global is not None
        ):
            self._finish_or_cancel(
                event.globalPosition().toPoint()
            )

            event.accept()
            return

        super().mouseReleaseEvent(
            event
        )

    def mouseDoubleClickEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        if (
            event.button()
            != Qt.MouseButton.LeftButton
        ):
            super().mouseDoubleClickEvent(
                event
            )
            return

        self._clear_drag_state()

        dock = self.parentWidget()

        if (
            dock is not None
            and isinstance(
                dock,
                QDockWidget,
            )
            and dock.isFloating()
        ):
            self.maximize_restore_requested.emit()
        else:
            self.float_requested.emit()

        event.accept()

    def cancel_drag(self) -> None:
        self._clear_drag_state()

    def _advance_drag(
        self,
        global_position: QPoint,
    ) -> None:
        if (
            self._press_global is None
            or self._press_dock_offset is None
        ):
            return

        if not self._drag_active:
            distance = (
                global_position
                - self._press_global
            ).manhattanLength()

            if (
                distance
                < QApplication.startDragDistance()
            ):
                return

            self._drag_active = True

            self.drag_started.emit(
                QPoint(global_position),
                QPoint(
                    self._press_dock_offset
                ),
            )

        self.drag_moved.emit(
            QPoint(global_position)
        )

    def _track_pointer(self) -> None:
        if self._press_global is None:
            self._tracking_timer.stop()
            return

        global_position = QCursor.pos()

        if not (
            QGuiApplication.mouseButtons()
            & Qt.MouseButton.LeftButton
        ):
            self._finish_or_cancel(
                global_position
            )
            return

        self._advance_drag(
            global_position
        )

    def _finish_or_cancel(
        self,
        global_position: QPoint,
    ) -> None:
        was_dragging = (
            self._drag_active
        )

        self._clear_drag_state()

        if was_dragging:
            self.drag_finished.emit(
                QPoint(global_position)
            )

    def _clear_drag_state(self) -> None:
        self._tracking_timer.stop()

        self._press_global = None
        self._press_dock_offset = None
        self._drag_active = False

    def _make_button(
        self,
        object_name: str,
        text: str,
        tooltip: str,
    ) -> QToolButton:
        button = QToolButton(self)

        button.setObjectName(
            object_name
        )
        button.setText(
            text
        )
        button.setToolTip(
            tooltip
        )
        button.setAutoRaise(
            True
        )
        button.setFocusPolicy(
            Qt.FocusPolicy.NoFocus
        )
        button.setFixedSize(
            28,
            26,
        )

        return button


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
        super().__init__(
            title,
            parent,
        )

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
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        self.setWidget(
            content
        )

        self.title_bar = WorkspaceTitleBar(
            self
        )

        self.title_bar.set_title(
            title
        )

        self.setTitleBarWidget(
            self.title_bar
        )

        self._drag_grab_offset = QPoint()
        self._drag_in_progress = False

        self._floating_window_ready = False
        self._normalizing_window_type = False

        # Не используем static QTimer.singleShot с bound
        # method. Таймер принадлежит WorkspaceDock и
        # уничтожается вместе с ним.
        self._floating_window_timer = QTimer(
            self
        )
        self._floating_window_timer.setSingleShot(
            True
        )
        self._floating_window_timer.setInterval(
            0
        )
        self._floating_window_timer.timeout.connect(
            self._ensure_real_floating_window
        )

        self.title_bar.drag_started.connect(
            self._on_title_drag_started
        )
        self.title_bar.drag_moved.connect(
            self._on_title_drag_moved
        )
        self.title_bar.drag_finished.connect(
            self._on_title_drag_finished
        )

        self.title_bar.float_requested.connect(
            self._on_float_requested
        )
        self.title_bar.minimize_requested.connect(
            self._on_minimize_requested
        )
        self.title_bar.maximize_restore_requested.connect(
            self._on_maximize_restore_requested
        )
        self.title_bar.close_requested.connect(
            self.close
        )

        self.windowTitleChanged.connect(
            self.title_bar.set_title
        )

        self.topLevelChanged.connect(
            self._on_top_level_changed
        )

        self.title_bar.set_floating(
            self.isFloating()
        )

    def closeEvent(
        self,
        event: QCloseEvent,
    ) -> None:
        self._floating_window_timer.stop()
        self.title_bar.cancel_drag()

        super().closeEvent(
            event
        )

        if not event.isAccepted():
            return

        self.closed.emit(
            self
        )

    def changeEvent(
        self,
        event: QEvent,
    ) -> None:
        super().changeEvent(
            event
        )

        if (
            event.type()
            == QEvent.Type.WindowStateChange
        ):
            self.title_bar.set_maximized(
                self.isMaximized()
            )

    def _on_title_drag_started(
        self,
        global_position: object,
        grab_offset: object,
    ) -> None:
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

        self._drag_in_progress = True

        resolved_offset = QPoint(
            grab_offset
        )

        if self.isMaximized():
            self.showNormal()

            resolved_offset = QPoint(
                max(
                    0,
                    self.width() // 2,
                ),
                min(
                    max(
                        0,
                        grab_offset.y(),
                    ),
                    max(
                        0,
                        self.title_bar.height() - 1,
                    ),
                ),
            )

        self._drag_grab_offset = QPoint(
            resolved_offset
        )

        self.drag_started.emit(
            self,
            QPoint(global_position),
            QPoint(resolved_offset),
        )

    def _on_title_drag_moved(
        self,
        global_position: object,
    ) -> None:
        if not isinstance(
            global_position,
            QPoint,
        ):
            return

        if self.isFloating():
            self.move(
                global_position
                - self._drag_grab_offset
            )

        self.drag_moved.emit(
            self,
            QPoint(global_position),
        )

    def _on_title_drag_finished(
        self,
        global_position: object,
    ) -> None:
        if not isinstance(
            global_position,
            QPoint,
        ):
            return

        self._drag_in_progress = False

        self.drag_finished.emit(
            self,
            QPoint(global_position),
        )

        self._drag_grab_offset = QPoint()

        if self.isFloating():
            self._schedule_floating_window_normalization()

    def _on_float_requested(self) -> None:
        if self.isFloating():
            return

        self.float_requested.emit(
            self
        )

    def _on_minimize_requested(self) -> None:
        if not self.isFloating():
            return

        self._floating_window_timer.stop()

        self._ensure_real_floating_window()

        self.showMinimized()

    def _on_maximize_restore_requested(
        self,
    ) -> None:
        if not self.isFloating():
            return

        self._floating_window_timer.stop()

        self._ensure_real_floating_window()

        if self.isMaximized():
            self.showNormal()
            return

        self.showMaximized()

    def _on_top_level_changed(
        self,
        floating: bool,
    ) -> None:
        self.title_bar.set_floating(
            floating
        )

        self.title_bar.set_maximized(
            self.isMaximized()
        )

        if not floating:
            self._floating_window_timer.stop()

            self._floating_window_ready = False
            self._normalizing_window_type = False
            return

        if self._drag_in_progress:
            return

        self._schedule_floating_window_normalization()

    def _schedule_floating_window_normalization(
        self,
    ) -> None:
        if not self.isFloating():
            self._floating_window_timer.stop()
            return

        if self._floating_window_ready:
            self._floating_window_timer.stop()
            return

        self._floating_window_timer.start()

    def _ensure_real_floating_window(
        self,
    ) -> None:
        if not self.isFloating():
            return

        if self._floating_window_ready:
            return

        if self._normalizing_window_type:
            return

        if (
            self.windowType()
            == Qt.WindowType.Window
        ):
            self._floating_window_ready = True
            return

        self._normalizing_window_type = True

        geometry = self.geometry()

        current_flags = self.windowFlags()

        non_type_flags = (
            current_flags
            & ~Qt.WindowType.WindowType_Mask
        )

        window_flags = (
            non_type_flags
            | Qt.WindowType.Window
        )

        self.setWindowFlags(
            window_flags
        )

        self.setGeometry(
            geometry
        )

        self.show()
        self.raise_()
        self.activateWindow()

        self._normalizing_window_type = False
        self._floating_window_ready = True