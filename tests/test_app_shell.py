from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
)

from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.workspace_dock import WorkspaceDock
from lodandsy.ui.workspace_placement import (
    WorkspacePlacement,
)


def _make_dock(
    window: AppShell,
    key: str = "test",
) -> WorkspaceDock:
    return WorkspaceDock(
        key=key,
        title=key.title(),
        content=QLabel("Content"),
        parent=window,
    )


def _simulate_custom_drop(
    window: AppShell,
    dock: WorkspaceDock,
    placement: WorkspacePlacement,
) -> None:
    window._dragging_workspace_dock = dock
    window._active_workspace_drop_zone = placement

    dock.drag_finished.emit(
        dock,
        QPoint(
            500,
            500,
        ),
    )


def test_app_shell_has_expected_structure(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    window.show()

    assert (
        window.centralWidget()
        is window.central_surface
    )

    assert (
        window.toolBarArea(window.left_rail)
        == Qt.ToolBarArea.LeftToolBarArea
    )

    assert (
        window.toolBarArea(window.right_rail)
        == Qt.ToolBarArea.RightToolBarArea
    )

    assert (
        window.toolBarArea(window.tree_host)
        == Qt.ToolBarArea.LeftToolBarArea
    )

    assert (
        window.toolBarArea(window.inspector_host)
        == Qt.ToolBarArea.RightToolBarArea
    )

    assert not window.left_rail.isMovable()
    assert not window.left_rail.isFloatable()

    assert not window.right_rail.isMovable()
    assert not window.right_rail.isFloatable()

    assert not window.tree_host.isMovable()
    assert not window.tree_host.isFloatable()

    assert not window.inspector_host.isMovable()
    assert not window.inspector_host.isFloatable()

    assert (
        window.dockWidgetArea(
            window.tree_panel
        )
        == Qt.DockWidgetArea.NoDockWidgetArea
    )

    assert (
        window.dockWidgetArea(
            window.inspector_panel
        )
        == Qt.DockWidgetArea.NoDockWidgetArea
    )

    assert (
        window.tree_panel.features()
        == QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
    )

    assert (
        window.inspector_panel.features()
        == QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
    )

    assert window.isDockNestingEnabled()

    assert (
        window.dockOptions()
        & QMainWindow.DockOption.AllowNestedDocks
    )

    assert (
        window.dockOptions()
        & QMainWindow.DockOption.AllowTabbedDocks
    )


def test_side_panels_can_be_toggled(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    window.show()

    assert window.tree_host.isVisible()
    assert window.inspector_host.isVisible()

    window.left_rail.tree_action.trigger()
    window.right_rail.inspector_action.trigger()

    assert not window.tree_host.isVisible()
    assert not window.inspector_host.isVisible()

    window.left_rail.tree_action.trigger()
    window.right_rail.inspector_action.trigger()

    assert window.tree_host.isVisible()
    assert window.inspector_host.isVisible()


def test_workspace_dock_uses_workspace_placement(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    dock = _make_dock(
        window
    )

    window.add_workspace_dock(
        dock,
        WorkspacePlacement.LEFT,
    )

    window.show()

    assert (
        window.dockWidgetArea(dock)
        == Qt.DockWidgetArea.LeftDockWidgetArea
    )

    assert (
        window.dockWidgetArea(
            window.tree_panel
        )
        == Qt.DockWidgetArea.NoDockWidgetArea
    )

    assert window.tree_host.isVisible()
    assert window.inspector_host.isVisible()

    assert dock in window.workspace_docks()


def test_workspace_dock_can_be_centered(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    dock = _make_dock(
        window
    )

    window.add_workspace_dock(
        dock,
        WorkspacePlacement.LEFT,
    )

    window.show()

    window.place_workspace_dock(
        dock,
        WorkspacePlacement.CENTER,
    )

    assert window.is_workspace_dock_centered(
        dock
    )

    assert not dock.isFloating()

    assert (
        window.central_surface.maximumWidth()
        == 0
    )

    assert (
        window.central_surface.maximumHeight()
        == 0
    )

    assert window.tree_host.isVisible()
    assert window.inspector_host.isVisible()

    qtbot.waitUntil(
        lambda: (
            dock.width()
            > window.WORKSPACE_SIDE_DOCK_SIZE
        ),
        timeout=1000,
    )


def test_custom_center_drop_uses_full_workspace(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    dock = _make_dock(
        window
    )

    window.add_workspace_dock(
        dock,
        WorkspacePlacement.LEFT,
    )

    window.show()

    window.place_workspace_dock(
        dock,
        WorkspacePlacement.FLOATING,
    )

    qtbot.waitUntil(
        dock.isFloating,
        timeout=1000,
    )

    _simulate_custom_drop(
        window,
        dock,
        WorkspacePlacement.CENTER,
    )

    qtbot.waitUntil(
        lambda: (
            window.is_workspace_dock_centered(
                dock
            )
        ),
        timeout=1000,
    )

    assert not dock.isFloating()

    assert (
        window.central_surface.maximumWidth()
        == 0
    )

    assert (
        window.central_surface.maximumHeight()
        == 0
    )


def test_custom_left_drop_uses_left_area(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    dock = _make_dock(
        window
    )

    window.add_workspace_dock(
        dock,
        WorkspacePlacement.RIGHT,
    )

    window.show()

    window.place_workspace_dock(
        dock,
        WorkspacePlacement.FLOATING,
    )

    qtbot.waitUntil(
        dock.isFloating,
        timeout=1000,
    )

    _simulate_custom_drop(
        window,
        dock,
        WorkspacePlacement.LEFT,
    )

    qtbot.waitUntil(
        lambda: (
            not dock.isFloating()
            and window.dockWidgetArea(dock)
            == Qt.DockWidgetArea.LeftDockWidgetArea
        ),
        timeout=1000,
    )

    assert not window.is_workspace_dock_centered(
        dock
    )


def test_second_left_dock_is_inserted_next_to_first(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    alpha = _make_dock(
        window,
        "alpha",
    )
    beta = _make_dock(
        window,
        "beta",
    )

    window.add_workspace_dock(
        alpha,
        WorkspacePlacement.LEFT,
    )

    window.add_workspace_dock(
        beta,
        WorkspacePlacement.RIGHT,
    )

    window.resize(
        1400,
        850,
    )
    window.show()

    window.place_workspace_dock(
        beta,
        WorkspacePlacement.FLOATING,
    )

    qtbot.waitUntil(
        beta.isFloating,
        timeout=1000,
    )

    _simulate_custom_drop(
        window,
        beta,
        WorkspacePlacement.LEFT,
    )

    qtbot.waitUntil(
        lambda: (
            not beta.isFloating()
            and window.dockWidgetArea(beta)
            == Qt.DockWidgetArea.LeftDockWidgetArea
        ),
        timeout=1000,
    )

    qtbot.waitUntil(
        lambda: (
            alpha.geometry().center().x()
            < beta.geometry().center().x()
        ),
        timeout=1000,
    )


def test_second_right_dock_is_inserted_next_to_workspace(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    alpha = _make_dock(
        window,
        "alpha",
    )
    beta = _make_dock(
        window,
        "beta",
    )

    window.add_workspace_dock(
        alpha,
        WorkspacePlacement.RIGHT,
    )

    window.add_workspace_dock(
        beta,
        WorkspacePlacement.LEFT,
    )

    window.resize(
        1400,
        850,
    )
    window.show()

    window.place_workspace_dock(
        beta,
        WorkspacePlacement.FLOATING,
    )

    qtbot.waitUntil(
        beta.isFloating,
        timeout=1000,
    )

    _simulate_custom_drop(
        window,
        beta,
        WorkspacePlacement.RIGHT,
    )

    qtbot.waitUntil(
        lambda: (
            not beta.isFloating()
            and window.dockWidgetArea(beta)
            == Qt.DockWidgetArea.RightDockWidgetArea
        ),
        timeout=1000,
    )

    qtbot.waitUntil(
        lambda: (
            beta.geometry().center().x()
            < alpha.geometry().center().x()
        ),
        timeout=1000,
    )


def test_second_top_dock_is_inserted_next_to_first(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    alpha = _make_dock(
        window,
        "alpha",
    )
    beta = _make_dock(
        window,
        "beta",
    )

    window.add_workspace_dock(
        alpha,
        WorkspacePlacement.TOP,
    )

    window.add_workspace_dock(
        beta,
        WorkspacePlacement.LEFT,
    )

    window.resize(
        1400,
        850,
    )
    window.show()

    window.place_workspace_dock(
        beta,
        WorkspacePlacement.FLOATING,
    )

    qtbot.waitUntil(
        beta.isFloating,
        timeout=1000,
    )

    _simulate_custom_drop(
        window,
        beta,
        WorkspacePlacement.TOP,
    )

    qtbot.waitUntil(
        lambda: (
            not beta.isFloating()
            and window.dockWidgetArea(beta)
            == Qt.DockWidgetArea.TopDockWidgetArea
        ),
        timeout=1000,
    )

    qtbot.waitUntil(
        lambda: (
            alpha.geometry().center().y()
            < beta.geometry().center().y()
        ),
        timeout=1000,
    )


def test_second_bottom_dock_is_inserted_next_to_workspace(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    alpha = _make_dock(
        window,
        "alpha",
    )
    beta = _make_dock(
        window,
        "beta",
    )

    window.add_workspace_dock(
        alpha,
        WorkspacePlacement.BOTTOM,
    )

    window.add_workspace_dock(
        beta,
        WorkspacePlacement.LEFT,
    )

    window.resize(
        1400,
        850,
    )
    window.show()

    window.place_workspace_dock(
        beta,
        WorkspacePlacement.FLOATING,
    )

    qtbot.waitUntil(
        beta.isFloating,
        timeout=1000,
    )

    _simulate_custom_drop(
        window,
        beta,
        WorkspacePlacement.BOTTOM,
    )

    qtbot.waitUntil(
        lambda: (
            not beta.isFloating()
            and window.dockWidgetArea(beta)
            == Qt.DockWidgetArea.BottomDockWidgetArea
        ),
        timeout=1000,
    )

    qtbot.waitUntil(
        lambda: (
            beta.geometry().center().y()
            < alpha.geometry().center().y()
        ),
        timeout=1000,
    )


def test_moving_centered_dock_restores_workspace(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    dock = _make_dock(
        window
    )

    window.add_workspace_dock(
        dock,
        WorkspacePlacement.LEFT,
    )

    window.show()

    window.place_workspace_dock(
        dock,
        WorkspacePlacement.CENTER,
    )

    assert window.is_workspace_dock_centered(
        dock
    )

    window.place_workspace_dock(
        dock,
        WorkspacePlacement.LEFT,
    )

    assert not window.is_workspace_dock_centered(
        dock
    )

    assert (
        window.central_surface.maximumWidth()
        > 0
    )

    assert (
        window.central_surface.maximumHeight()
        > 0
    )

    assert (
        window.dockWidgetArea(dock)
        == Qt.DockWidgetArea.LeftDockWidgetArea
    )


def test_closing_centered_dock_restores_workspace(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    dock = _make_dock(
        window
    )

    window.add_workspace_dock(
        dock,
        WorkspacePlacement.LEFT,
    )

    window.show()

    window.place_workspace_dock(
        dock,
        WorkspacePlacement.CENTER,
    )

    assert window.is_workspace_dock_centered(
        dock
    )

    dock.close()

    qtbot.waitUntil(
        lambda: not dock.isVisible(),
        timeout=1000,
    )

    assert not window.is_workspace_dock_centered(
        dock
    )

    assert (
        window.central_surface.maximumWidth()
        > 0
    )

    assert (
        window.central_surface.maximumHeight()
        > 0
    )


def test_workspace_dock_can_be_removed(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    dock = _make_dock(
        window
    )

    window.add_workspace_dock(
        dock,
        WorkspacePlacement.LEFT,
    )

    assert dock in window.workspace_docks()

    window.remove_workspace_dock(
        dock
    )

    assert dock not in window.workspace_docks()

    assert (
        window.dockWidgetArea(dock)
        == Qt.DockWidgetArea.NoDockWidgetArea
    )


def test_one_placement_method_moves_between_all_states(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    dock = _make_dock(
        window
    )

    window.add_workspace_dock(
        dock,
        WorkspacePlacement.LEFT,
    )

    window.show()

    window.place_workspace_dock(
        dock,
        WorkspacePlacement.RIGHT,
    )

    assert (
        window.dockWidgetArea(dock)
        == Qt.DockWidgetArea.RightDockWidgetArea
    )

    window.place_workspace_dock(
        dock,
        WorkspacePlacement.TOP,
    )

    assert (
        window.dockWidgetArea(dock)
        == Qt.DockWidgetArea.TopDockWidgetArea
    )

    window.place_workspace_dock(
        dock,
        WorkspacePlacement.BOTTOM,
    )

    assert (
        window.dockWidgetArea(dock)
        == Qt.DockWidgetArea.BottomDockWidgetArea
    )

    window.place_workspace_dock(
        dock,
        WorkspacePlacement.CENTER,
    )

    assert window.is_workspace_dock_centered(
        dock
    )

    window.place_workspace_dock(
        dock,
        WorkspacePlacement.FLOATING,
    )

    assert dock.isFloating()

    assert not window.is_workspace_dock_centered(
        dock
    )

    assert (
        window.central_surface.maximumWidth()
        > 0
    )


def test_custom_drop_uses_same_placement_pipeline(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    dock = _make_dock(
        window
    )

    window.add_workspace_dock(
        dock,
        WorkspacePlacement.LEFT,
    )

    window.show()

    window.place_workspace_dock(
        dock,
        WorkspacePlacement.FLOATING,
    )

    qtbot.waitUntil(
        dock.isFloating,
        timeout=1000,
    )

    _simulate_custom_drop(
        window,
        dock,
        WorkspacePlacement.RIGHT,
    )

    qtbot.waitUntil(
        lambda: (
            not dock.isFloating()
            and window.dockWidgetArea(dock)
            == Qt.DockWidgetArea.RightDockWidgetArea
        ),
        timeout=1000,
    )

    assert not window.is_workspace_dock_centered(
        dock
    )