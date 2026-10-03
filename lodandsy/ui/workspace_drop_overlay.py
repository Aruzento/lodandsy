from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import QWidget


class WorkspaceDropOverlay(QWidget):
    TARGET_SIZE = 96

    def __init__(
        self,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)

        self.setObjectName(
            "workspaceDropOverlay"
        )

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )

        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.setAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating,
            True,
        )
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )

        self._center_active = False

        self.hide()

    @property
    def center_active(self) -> bool:
        return self._center_active

    def center_target_rect(self) -> QRect:
        target = QRect(
            0,
            0,
            self.TARGET_SIZE,
            self.TARGET_SIZE,
        )

        target.moveCenter(
            self.rect().center()
        )

        return target

    def show_for_global_position(
        self,
        global_position: QPoint,
        workspace_rect: QRect,
    ) -> bool:
        if not workspace_rect.contains(
            global_position
        ):
            self.hide_overlay()
            return False

        self.setGeometry(
            workspace_rect
        )

        local_position = (
            global_position
            - workspace_rect.topLeft()
        )

        self._center_active = (
            self.center_target_rect().contains(
                local_position
            )
        )

        self.show()
        self.raise_()
        self.update()

        return self._center_active

    def hide_overlay(self) -> None:
        self._center_active = False
        self.hide()

    def paintEvent(
        self,
        _event,
    ) -> None:
        painter = QPainter(self)

        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True,
        )

        highlight = self.palette().color(
            QPalette.ColorRole.Highlight
        )

        if self._center_active:
            workspace_fill = QColor(
                highlight
            )
            workspace_fill.setAlpha(70)

            workspace_border = QColor(
                highlight
            )
            workspace_border.setAlpha(220)

            painter.fillRect(
                self.rect(),
                workspace_fill,
            )

            painter.setPen(
                QPen(
                    workspace_border,
                    3,
                )
            )

            painter.drawRect(
                self.rect().adjusted(
                    2,
                    2,
                    -3,
                    -3,
                )
            )

        target_rect = self.center_target_rect()

        target_fill = QColor(
            highlight
        )
        target_fill.setAlpha(
            220
            if self._center_active
            else 150
        )

        target_border = QColor(
            highlight
        )
        target_border.setAlpha(255)

        painter.setBrush(
            target_fill
        )

        painter.setPen(
            QPen(
                target_border,
                3,
            )
        )

        painter.drawRoundedRect(
            target_rect,
            10,
            10,
        )

        inner_size = 34

        inner_rect = QRect(
            0,
            0,
            inner_size,
            inner_size,
        )

        inner_rect.moveCenter(
            target_rect.center()
        )

        inner_fill = QColor(
            self.palette().color(
                QPalette.ColorRole.Window
            )
        )
        inner_fill.setAlpha(210)

        painter.setBrush(
            inner_fill
        )

        painter.drawRoundedRect(
            inner_rect,
            5,
            5,
        )