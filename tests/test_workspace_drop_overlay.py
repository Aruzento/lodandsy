from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QWidget

from lodandsy.ui.workspace_drop_overlay import (
    WorkspaceDropOverlay,
)


def test_center_target_activates_in_center(
    qtbot,
) -> None:
    parent = QWidget()
    parent.resize(
        800,
        600,
    )

    qtbot.addWidget(parent)

    parent.show()

    overlay = WorkspaceDropOverlay(
        parent
    )

    workspace_rect = QRect(
        parent.mapToGlobal(
            QPoint(
                0,
                0,
            )
        ),
        parent.size(),
    )

    active = overlay.show_for_global_position(
        workspace_rect.center(),
        workspace_rect,
    )

    assert active
    assert overlay.center_active
    assert overlay.isVisible()
    assert overlay.isWindow()


def test_center_target_is_inactive_away_from_center(
    qtbot,
) -> None:
    parent = QWidget()
    parent.resize(
        800,
        600,
    )

    qtbot.addWidget(parent)

    parent.show()

    overlay = WorkspaceDropOverlay(
        parent
    )

    workspace_rect = QRect(
        parent.mapToGlobal(
            QPoint(
                0,
                0,
            )
        ),
        parent.size(),
    )

    position = (
        workspace_rect.topLeft()
        + QPoint(
            20,
            20,
        )
    )

    active = overlay.show_for_global_position(
        position,
        workspace_rect,
    )

    assert not active
    assert not overlay.center_active
    assert overlay.isVisible()


def test_overlay_hides_outside_workspace(
    qtbot,
) -> None:
    parent = QWidget()
    parent.resize(
        800,
        600,
    )

    qtbot.addWidget(parent)

    parent.show()

    overlay = WorkspaceDropOverlay(
        parent
    )

    workspace_rect = QRect(
        parent.mapToGlobal(
            QPoint(
                0,
                0,
            )
        ),
        parent.size(),
    )

    active = overlay.show_for_global_position(
        QPoint(
            -10000,
            -10000,
        ),
        workspace_rect,
    )

    assert not active
    assert not overlay.center_active
    assert not overlay.isVisible()