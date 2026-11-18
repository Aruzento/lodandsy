import pytest
from PySide6.QtWidgets import QLabel

from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.window_manager import WindowManager


def make_manager(qtbot):
    shell = AppShell()
    qtbot.addWidget(shell)
    shell.show()
    return shell, WindowManager(shell)


def test_window_manager_opens_workspace_window(qtbot):
    shell, manager = make_manager(qtbot)
    window = manager.open_window("test", "Test", lambda: QLabel("Content"))
    assert manager.find_window("test") is window
    assert window.key == "test"
    assert window.windowTitle() == "Test"
    assert window.widget().text() == "Content"
    assert window.dock in shell.workspace.dockWidgetsMap().values()


def test_repeated_open_returns_existing_window(qtbot):
    shell, manager = make_manager(qtbot)
    calls = []
    def factory():
        calls.append(True)
        return QLabel("Content")
    first = manager.open_window("same", "First", factory)
    assert manager.open_window("same", "Second", factory) is first
    assert len(calls) == 1 and manager.window_keys() == ("same",)


def test_focus_window_shows_existing_window(qtbot):
    shell, manager = make_manager(qtbot)
    window = manager.open_window("test", "Test", lambda: QLabel("Content"))
    window.dock.hide()
    assert not window.dock.isVisible()
    assert manager.focus_window("test") is window
    assert window.dock.isVisible()


def test_focus_unknown_window_returns_none(qtbot):
    shell, manager = make_manager(qtbot)
    assert manager.focus_window("missing") is None


def test_close_window_removes_it_from_registry(qtbot):
    shell, manager = make_manager(qtbot)
    window = manager.open_window("test", "Test", lambda: QLabel("Content"))
    assert manager.close_window("test")
    assert manager.find_window("test") is None
    assert window.dock not in shell.workspace.dockWidgetsMap().values()


def test_closed_key_can_be_opened_again(qtbot):
    shell, manager = make_manager(qtbot)
    first = manager.open_window("test", "Test", lambda: QLabel("Content"))
    assert manager.close_window("test")
    second = manager.open_window("test", "Test", lambda: QLabel("Content"))
    assert second is not first and manager.find_window("test") is second
    assert list(shell.workspace.dockWidgetsMap().values()) == [second.dock]


def test_close_unknown_window_returns_false(qtbot):
    shell, manager = make_manager(qtbot)
    assert not manager.close_window("missing")


def test_invalid_factory_does_not_register_a_window(qtbot):
    shell, manager = make_manager(qtbot)
    with pytest.raises(TypeError, match="QWidget"):
        manager.open_window("bad", "Bad", lambda: object())
    assert manager.window_keys() == ()
