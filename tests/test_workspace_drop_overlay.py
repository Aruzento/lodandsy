from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QWidget

from lodandsy.ui.workspace_drop_overlay import (
    WorkspaceDropOverlay,
)


def _make_workspace_rect(
    parent: QWidget,
) -> QRect:
    return QRect(
        parent.mapToGlobal(
            QPoint(
                0,
                0,
            )
        ),
        parent.size(),
    )


def test_overlay_is_child_of_workspace_window(
    qtbot,
) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)

    overlay = WorkspaceDropOverlay(
        parent
    )

    assert not overlay.isWindow()

    assert (
        overlay.parentWidget()
        is parent
    )

    assert overlay.testAttribute(
        Qt.WidgetAttribute.WA_TransparentForMouseEvents
    )


def test_center_zone_activates_in_center(
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

    workspace_rect = _make_workspace_rect(
        parent
    )

    active_zone = overlay.show_for_global_position(
        workspace_rect.center(),
        workspace_rect,
    )

    assert (
        active_zone
        == WorkspaceDropOverlay.ZONE_CENTER
    )

    assert (
        overlay.active_zone
        == WorkspaceDropOverlay.ZONE_CENTER
    )

    assert overlay.isVisible()


def test_left_zone_activates_on_left_side(
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

    workspace_rect = _make_workspace_rect(
        parent
    )

    position = (
        workspace_rect.topLeft()
        + QPoint(
            20,
            workspace_rect.height() // 2,
        )
    )

    active_zone = overlay.show_for_global_position(
        position,
        workspace_rect,
    )

    assert (
        active_zone
        == WorkspaceDropOverlay.ZONE_LEFT
    )

    assert overlay.isVisible()


def test_gap_between_zones_stays_inactive(
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

    workspace_rect = _make_workspace_rect(
        parent
    )

    position = (
        workspace_rect.topLeft()
        + QPoint(
            180,
            180,
        )
    )

    active_zone = overlay.show_for_global_position(
        position,
        workspace_rect,
    )

    assert active_zone is None
    assert overlay.active_zone is None
    assert not overlay.isVisible()


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

    workspace_rect = _make_workspace_rect(
        parent
    )

    active_zone = overlay.show_for_global_position(
        QPoint(
            -10000,
            -10000,
        ),
        workspace_rect,
    )

    assert active_zone is None
    assert overlay.active_zone is None
    assert not overlay.isVisible()