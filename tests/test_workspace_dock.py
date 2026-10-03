from PySide6.QtCore import (
    QEvent,
    QPoint,
    QPointF,
    Qt,
)
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
)

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


def test_workspace_dock_disables_native_drag(
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
        & dock.DockWidgetFeature.DockWidgetFloatable
    )

    assert not (
        features
        & dock.DockWidgetFeature.DockWidgetMovable
    )


def test_docked_title_drag_enters_custom_pipeline(
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

    qtbot.waitUntil(
        lambda: (
            dock.widget().geometry().top()
            > 0
        ),
        timeout=1000,
    )

    title_y = max(
        1,
        dock.widget().geometry().top() // 2,
    )

    start_local = QPoint(
        80,
        title_y,
    )

    start_global = dock.mapToGlobal(
        start_local
    )

    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(start_local),
        QPointF(start_global),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )

    dock.mousePressEvent(
        press_event
    )

    distance = (
        QApplication.startDragDistance()
        + 20
    )

    move_local = (
        start_local
        + QPoint(
            distance,
            0,
        )
    )

    move_global = dock.mapToGlobal(
        move_local
    )

    move_event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(move_local),
        QPointF(move_global),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )

    dock.mouseMoveEvent(
        move_event
    )

    assert dock.isFloating()

    assert (
        window._dragging_workspace_dock
        is dock
    )

    assert (
        dock.allowedAreas()
        == Qt.DockWidgetArea.NoDockWidgetArea
    )

    dock.close()


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

    window.place_workspace_dock(
        dock,
        "floating",
    )

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

    assert dock.widget() is content

    window.place_workspace_dock(
        dock,
        "left",
    )

    qtbot.waitUntil(
        lambda: not dock.isFloating(),
        timeout=1000,
    )

    assert dock.widget() is content


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