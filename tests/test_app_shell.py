from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
)

from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.workspace_dock import WorkspaceDock


def test_app_shell_has_expected_structure(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    window.show()

    assert window.centralWidget() is window.central_surface

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
        window.dockWidgetArea(window.tree_panel)
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

    assert not window.isDockNestingEnabled()

    assert (
        window.dockOptions()
        & QMainWindow.DockOption.AllowTabbedDocks
    )

    assert not (
        window.dockOptions()
        & QMainWindow.DockOption.AllowNestedDocks
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


def test_workspace_dock_uses_workspace_dock_area(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    dock = WorkspaceDock(
        key="test",
        title="Test",
        content=QLabel("Content"),
        parent=window,
    )

    window.add_workspace_dock(
        dock,
        Qt.DockWidgetArea.LeftDockWidgetArea,
    )

    window.show()

    assert (
        window.dockWidgetArea(dock)
        == Qt.DockWidgetArea.LeftDockWidgetArea
    )

    assert (
        window.dockWidgetArea(window.tree_panel)
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

    dock = WorkspaceDock(
        key="test",
        title="Test",
        content=QLabel("Content"),
        parent=window,
    )

    window.add_workspace_dock(
        dock
    )

    window.show()

    window.center_workspace_dock(
        dock
    )

    assert (
        window.is_workspace_dock_centered(
            dock
        )
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


def test_restoring_centered_dock_restores_workspace(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    dock = WorkspaceDock(
        key="test",
        title="Test",
        content=QLabel("Content"),
        parent=window,
    )

    window.add_workspace_dock(
        dock
    )

    window.show()

    window.center_workspace_dock(
        dock
    )

    window.restore_workspace_dock_size(
        dock
    )

    assert not (
        window.is_workspace_dock_centered(
            dock
        )
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

    dock = WorkspaceDock(
        key="test",
        title="Test",
        content=QLabel("Content"),
        parent=window,
    )

    window.add_workspace_dock(
        dock
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