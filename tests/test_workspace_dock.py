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
from lodandsy.ui.workspace_placement import (
    WorkspacePlacement,
)


def _make_dock(
    window: AppShell,
) -> WorkspaceDock:
    return WorkspaceDock(
        key="test",
        title="Test window",
        content=QLabel("Content"),
        parent=window,
    )


def _drag_title_bar(
    dock: WorkspaceDock,
    target_global: QPoint,
) -> None:
    title_bar = dock.title_bar

    start_local = QPoint(
        80,
        max(
            1,
            title_bar.height() // 2,
        ),
    )

    start_global = (
        title_bar.mapToGlobal(
            start_local
        )
    )

    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(start_local),
        QPointF(start_global),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )

    title_bar.mousePressEvent(
        press_event
    )

    move_local = (
        title_bar.mapFromGlobal(
            target_global
        )
    )

    move_event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(move_local),
        QPointF(target_global),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )

    title_bar.mouseMoveEvent(
        move_event
    )


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

    assert (
        dock.titleBarWidget()
        is dock.title_bar
    )


def test_workspace_dock_disables_native_drag(
    qtbot,
) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    dock = _make_dock(
        window
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

    dock = _make_dock(
        window
    )

    window.add_workspace_dock(
        dock,
        WorkspacePlacement.LEFT,
    )

    window.show()

    title_bar = dock.title_bar

    target = (
        title_bar.mapToGlobal(
            QPoint(
                80,
                title_bar.height() // 2,
            )
        )
        + QPoint(
            QApplication.startDragDistance()
            + 40,
            0,
        )
    )

    _drag_title_bar(
        dock,
        target,
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

    dock.title_bar.cancel_drag()
    dock.close()


def test_floating_title_drag_uses_same_pipeline(
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

    qtbot.waitUntil(
        lambda: (
            dock.windowType()
            == Qt.WindowType.Window
        ),
        timeout=1000,
    )

    workspace_rect = (
        window._workspace_global_rect()
    )

    target = QPoint(
        workspace_rect.center().x(),
        workspace_rect.top() + 20,
    )

    _drag_title_bar(
        dock,
        target,
    )

    assert (
        window._dragging_workspace_dock
        is dock
    )

    assert (
        window._active_workspace_drop_zone
        == WorkspacePlacement.TOP
    )

    assert (
        window.workspace_drop_overlay.isVisible()
    )

    dock.title_bar.cancel_drag()
    dock.close()


def test_floating_workspace_is_real_window(
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
        lambda: (
            dock.isFloating()
            and dock.windowType()
            == Qt.WindowType.Window
        ),
        timeout=1000,
    )

    assert dock.isWindow()

    assert (
        dock.windowType()
        == Qt.WindowType.Window
    )


def test_floating_workspace_can_maximize_and_restore(
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
        lambda: (
            dock.windowType()
            == Qt.WindowType.Window
        ),
        timeout=1000,
    )

    dock.title_bar.maximize_button.click()

    qtbot.waitUntil(
        dock.isMaximized,
        timeout=1000,
    )

    assert dock.isVisible()

    dock.title_bar.maximize_button.click()

    qtbot.waitUntil(
        lambda: not dock.isMaximized(),
        timeout=1000,
    )

    assert dock.isVisible()


def test_floating_workspace_can_minimize(
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
        lambda: (
            dock.windowType()
            == Qt.WindowType.Window
        ),
        timeout=1000,
    )

    dock.title_bar.minimize_button.click()

    qtbot.waitUntil(
        dock.isMinimized,
        timeout=1000,
    )

    dock.showNormal()

    qtbot.waitUntil(
        lambda: not dock.isMinimized(),
        timeout=1000,
    )

    assert dock.isVisible()


def test_title_bar_controls_change_with_floating_state(
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

    assert dock.title_bar.float_button.isVisible()
    assert not dock.title_bar.minimize_button.isVisible()
    assert not dock.title_bar.maximize_button.isVisible()

    window.place_workspace_dock(
        dock,
        WorkspacePlacement.FLOATING,
    )

    qtbot.waitUntil(
        dock.isFloating,
        timeout=1000,
    )

    assert not dock.title_bar.float_button.isVisible()
    assert dock.title_bar.minimize_button.isVisible()
    assert dock.title_bar.maximize_button.isVisible()
    assert dock.title_bar.close_button.isVisible()


def test_pending_floating_normalization_stops_on_close(
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

    dock._floating_window_ready = False

    dock._schedule_floating_window_normalization()

    assert dock._floating_window_timer.isActive()

    dock.close()

    assert not dock._floating_window_timer.isActive()

    # Даём Qt обработать очередь событий.
    # pytest-qt сам провалит тест, если после
    # закрытия возникнет исключение в event loop.
    qtbot.wait(
        10
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
        dock,
        WorkspacePlacement.LEFT,
    )

    window.show()

    assert not dock.isFloating()

    window.place_workspace_dock(
        dock,
        WorkspacePlacement.FLOATING,
    )

    qtbot.waitUntil(
        lambda: (
            dock.isFloating()
            and dock.windowType()
            == Qt.WindowType.Window
        ),
        timeout=1000,
    )

    assert dock.widget() is content

    window.place_workspace_dock(
        dock,
        WorkspacePlacement.LEFT,
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

    dock = _make_dock(
        window
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