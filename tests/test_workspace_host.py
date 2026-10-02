from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QWidget

from lodandsy.ui.workspace_dock import WorkspaceDock
from lodandsy.ui.workspace_host import WorkspaceHost


def test_workspace_host_is_embedded_widget(
    qtbot,
) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)

    host = WorkspaceHost(parent)

    assert host.objectName() == "workspaceHost"
    assert host.parent() is parent
    assert not host.isWindow()

    assert host.centralWidget() is not None

    assert (
        host.centralWidget().size()
        == QSize(0, 0)
    )


def test_workspace_host_disables_nested_docking(
    qtbot,
) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)

    host = WorkspaceHost(parent)

    options = host.dockOptions()

    assert not host.isDockNestingEnabled()

    assert (
        options
        & host.DockOption.AllowTabbedDocks
    )

    assert (
        options
        & host.DockOption.ForceTabbedDocks
    )

    assert not (
        options
        & host.DockOption.AllowNestedDocks
    )


def test_workspace_host_adds_dock(
    qtbot,
) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)

    host = WorkspaceHost(parent)

    dock = WorkspaceDock(
        key="card:one",
        title="Card",
        content=QLabel("Content"),
        parent=host,
    )

    host.add_workspace_dock(
        dock
    )

    assert dock in host.workspace_docks()

    assert (
        host.dockWidgetArea(dock)
        == Qt.DockWidgetArea.LeftDockWidgetArea
    )


def test_workspace_host_tabs_docks_in_same_area(
    qtbot,
) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)

    host = WorkspaceHost(parent)

    first = WorkspaceDock(
        key="card:first",
        title="First",
        content=QLabel("First"),
        parent=host,
    )

    second = WorkspaceDock(
        key="card:second",
        title="Second",
        content=QLabel("Second"),
        parent=host,
    )

    host.add_workspace_dock(
        first
    )

    host.add_workspace_dock(
        second
    )

    tabified = host.tabifiedDockWidgets(
        first
    )

    assert second in tabified


def test_workspace_host_removes_dock(
    qtbot,
) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)

    host = WorkspaceHost(parent)

    dock = WorkspaceDock(
        key="card:one",
        title="Card",
        content=QLabel("Content"),
        parent=host,
    )

    host.add_workspace_dock(
        dock
    )

    host.remove_workspace_dock(
        dock
    )

    assert dock not in host.workspace_docks()