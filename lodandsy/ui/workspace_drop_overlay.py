from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from lodandsy.ui.workspace_placement import (
    WorkspacePlacement,
)


class WorkspaceDropOverlay(QWidget):
    ZONE_LEFT = WorkspacePlacement.LEFT
    ZONE_TOP = WorkspacePlacement.TOP
    ZONE_RIGHT = WorkspacePlacement.RIGHT
    ZONE_BOTTOM = WorkspacePlacement.BOTTOM
    ZONE_CENTER = WorkspacePlacement.CENTER

    WORKSPACE_FILL = QColor(
        210,
        45,
        45,
        72,
    )
    WORKSPACE_BORDER = QColor(
        230,
        55,
        55,
        235,
    )

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

        self._active_zone: (
            WorkspacePlacement | None
        ) = None

        self.hide()

    @property
    def active_zone(
        self,
    ) -> WorkspacePlacement | None:
        return self._active_zone

    def show_for_global_position(
        self,
        global_position: QPoint,
        workspace_rect: QRect,
    ) -> WorkspacePlacement | None:
        if not workspace_rect.contains(
            global_position
        ):
            self.hide_overlay()
            return None

        # Сначала overlay получает точную геометрию
        # текущего workspace.
        #
        # Это обязательно должно произойти до
        # zone_at(), потому что зоны рассчитываются
        # через self.rect().
        self.setGeometry(
            workspace_rect
        )

        local_position = (
            global_position
            - workspace_rect.topLeft()
        )

        active_zone = self.zone_at(
            local_position
        )

        if active_zone is None:
            self.hide_overlay()
            return None

        self._active_zone = active_zone

        self.show()
        self.raise_()
        self.repaint()

        return self._active_zone

    def hide_overlay(self) -> None:
        self._active_zone = None
        self.hide()

    def zone_at(
        self,
        local_position: QPoint,
    ) -> WorkspacePlacement | None:
        zone_rects = self.zone_rects()

        if zone_rects[
            WorkspacePlacement.CENTER
        ].contains(local_position):
            return WorkspacePlacement.CENTER

        if zone_rects[
            WorkspacePlacement.TOP
        ].contains(local_position):
            return WorkspacePlacement.TOP

        if zone_rects[
            WorkspacePlacement.BOTTOM
        ].contains(local_position):
            return WorkspacePlacement.BOTTOM

        if zone_rects[
            WorkspacePlacement.LEFT
        ].contains(local_position):
            return WorkspacePlacement.LEFT

        if zone_rects[
            WorkspacePlacement.RIGHT
        ].contains(local_position):
            return WorkspacePlacement.RIGHT

        return None

    def zone_rects(
        self,
    ) -> dict[WorkspacePlacement, QRect]:
        rect = self.rect()

        width = rect.width()
        height = rect.height()

        short_side = max(
            1,
            min(width, height),
        )

        band = max(
            40,
            min(short_side // 7, 120),
        )

        center_size = max(
            120,
            short_side - band * 4,
        )

        center_rect = QRect(
            0,
            0,
            center_size,
            center_size,
        )
        center_rect.moveCenter(
            rect.center()
        )

        top_rect = QRect(
            0,
            0,
            width,
            band,
        )

        bottom_rect = QRect(
            0,
            height - band,
            width,
            band,
        )

        left_rect = QRect(
            0,
            band,
            band,
            height - band * 2,
        )

        right_rect = QRect(
            width - band,
            band,
            band,
            height - band * 2,
        )

        return {
            WorkspacePlacement.LEFT: left_rect,
            WorkspacePlacement.TOP: top_rect,
            WorkspacePlacement.RIGHT: right_rect,
            WorkspacePlacement.BOTTOM: bottom_rect,
            WorkspacePlacement.CENTER: center_rect,
        }

    def paintEvent(
        self,
        _event,
    ) -> None:
        if self._active_zone is None:
            return

        zone_rect = self.zone_rects()[
            self._active_zone
        ]

        painter = QPainter(self)

        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True,
        )

        painter.fillRect(
            zone_rect,
            self.WORKSPACE_FILL,
        )

        painter.setPen(
            QPen(
                self.WORKSPACE_BORDER,
                2,
            )
        )

        painter.drawRect(
            zone_rect.adjusted(
                1,
                1,
                -2,
                -2,
            )
        )