from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.workspace_dock import WorkspaceDock


def test_workspace_dock_wraps_content(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    content = QLabel("Content")

    dock = WorkspaceDock(
        key="test",
        title="Test window",
        content=content,
        parent=window,
    )

    window.add_workspace_dock(
        dock
    )

    assert dock.key == "test"

    assert (
        dock.objectName()
        == "workspaceDock:test"
    )

    assert dock.windowTitle() == "Test window"

    assert dock.widget() is content


def test_workspace_dock_has_working_window_features(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    dock = WorkspaceDock(
        key="test",
        title="Test window",
        content=QLabel("Content"),
        parent=window,
    )

    window.add_workspace_dock(
        dock
    )

    features = dock.features()

    assert (
        features
        & dock.DockWidgetFeature.DockWidgetClosable
    )

    assert (
        features
        & dock.DockWidgetFeature.DockWidgetMovable
    )

    assert (
        features
        & dock.DockWidgetFeature.DockWidgetFloatable
    )


def test_workspace_dock_can_float_and_return(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    content = QLabel("Content")

    dock = WorkspaceDock(
        key="test",
        title="Test window",
        content=content,
        parent=window,
    )

    window.add_workspace_dock(
        dock
    )

    window.show()

    assert not dock.isFloating()

    dock.setFloating(True)

    qtbot.waitUntil(
        dock.isFloating,
        timeout=1000,
    )

    qtbot.waitUntil(
        lambda: (
            dock.windowType()
            == Qt.WindowType.Window
        ),
        timeout=1000,
    )

    assert dock.isFloating()
    assert dock.widget() is content

    dock.setFloating(False)

    qtbot.waitUntil(
        lambda: not dock.isFloating(),
        timeout=1000,
    )

    assert not dock.isFloating()
    assert dock.widget() is content


def test_floating_workspace_dock_is_normal_window(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    dock = WorkspaceDock(
        key="test",
        title="Test window",
        content=QLabel("Content"),
        parent=window,
    )

    window.add_workspace_dock(
        dock
    )

    window.show()

    dock.setFloating(True)

    qtbot.waitUntil(
        dock.isFloating,
        timeout=1000,
    )

    qtbot.waitUntil(
        lambda: (
            dock.windowType()
            == Qt.WindowType.Window
        ),
        timeout=1000,
    )

    assert (
        dock.windowType()
        == Qt.WindowType.Window
    )

    flags = dock.windowFlags()

    assert (
        flags
        & Qt.WindowType.CustomizeWindowHint
    )

    assert (
        flags
        & Qt.WindowType.WindowTitleHint
    )

    assert (
        flags
        & Qt.WindowType.WindowSystemMenuHint
    )

    assert (
        flags
        & Qt.WindowType.WindowMinimizeButtonHint
    )

    assert (
        flags
        & Qt.WindowType.WindowMaximizeButtonHint
    )

    assert (
        flags
        & Qt.WindowType.WindowCloseButtonHint
    )


def test_workspace_dock_can_be_closed(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    dock = WorkspaceDock(
        key="test",
        title="Test window",
        content=QLabel("Content"),
        parent=window,
    )

    window.add_workspace_dock(
        dock
    )

    window.show()

    assert dock.isVisible()

    dock.close()

    qtbot.waitUntil(
        lambda: not dock.isVisible(),
        timeout=1000,
    )

    assert not dock.isVisible()