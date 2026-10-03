from PySide6.QtWidgets import QLabel

from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.window_manager import WindowManager
from lodandsy.ui.workspace_placement import (
    WorkspacePlacement,
)


def _make_window_manager(
    qtbot,
) -> tuple[
    AppShell,
    WindowManager,
]:
    shell = AppShell()

    qtbot.addWidget(
        shell
    )

    shell.show()

    manager = WindowManager(
        shell
    )

    return (
        shell,
        manager,
    )


def test_window_manager_opens_workspace_window(
    qtbot,
) -> None:
    shell, manager = (
        _make_window_manager(
            qtbot
        )
    )

    dock = manager.open_window(
        key="test",
        title="Test window",
        content_factory=lambda: QLabel(
            "Content"
        ),
        placement=WorkspacePlacement.LEFT,
    )

    assert (
        manager.find_window("test")
        is dock
    )

    assert (
        dock
        in shell.workspace_docks()
    )

    assert (
        dock.key
        == "test"
    )

    assert (
        dock.windowTitle()
        == "Test window"
    )


def test_repeated_open_returns_existing_window(
    qtbot,
) -> None:
    _shell, manager = (
        _make_window_manager(
            qtbot
        )
    )

    factory_calls = 0

    def create_content():
        nonlocal factory_calls

        factory_calls += 1

        return QLabel(
            f"Content {factory_calls}"
        )

    first = manager.open_window(
        key="same",
        title="First",
        content_factory=create_content,
    )

    second = manager.open_window(
        key="same",
        title="Second",
        content_factory=create_content,
        placement=WorkspacePlacement.RIGHT,
    )

    assert second is first

    assert factory_calls == 1

    assert (
        manager.window_keys()
        == ("same",)
    )


def test_focus_window_shows_existing_window(
    qtbot,
) -> None:
    _shell, manager = (
        _make_window_manager(
            qtbot
        )
    )

    dock = manager.open_window(
        key="test",
        title="Test",
        content_factory=lambda: QLabel(
            "Content"
        ),
    )

    dock.hide()

    assert not dock.isVisible()

    focused = manager.focus_window(
        "test"
    )

    assert focused is dock

    assert dock.isVisible()


def test_focus_unknown_window_returns_none(
    qtbot,
) -> None:
    _shell, manager = (
        _make_window_manager(
            qtbot
        )
    )

    assert (
        manager.focus_window(
            "missing"
        )
        is None
    )


def test_close_window_removes_it_from_registry(
    qtbot,
) -> None:
    shell, manager = (
        _make_window_manager(
            qtbot
        )
    )

    dock = manager.open_window(
        key="test",
        title="Test",
        content_factory=lambda: QLabel(
            "Content"
        ),
    )

    assert manager.close_window(
        "test"
    )

    assert (
        manager.find_window(
            "test"
        )
        is None
    )

    assert (
        dock
        not in shell.workspace_docks()
    )


def test_closed_key_can_be_opened_again(
    qtbot,
) -> None:
    shell, manager = (
        _make_window_manager(
            qtbot
        )
    )

    factory_calls = 0

    def create_content():
        nonlocal factory_calls

        factory_calls += 1

        return QLabel(
            f"Content {factory_calls}"
        )

    first = manager.open_window(
        key="test",
        title="Test",
        content_factory=create_content,
    )

    assert manager.close_window(
        "test"
    )

    second = manager.open_window(
        key="test",
        title="Test",
        content_factory=create_content,
    )

    assert second is not first

    assert factory_calls == 2

    assert (
        manager.find_window(
            "test"
        )
        is second
    )

    assert (
        shell.workspace_docks()
        == (second,)
    )


def test_close_unknown_window_returns_false(
    qtbot,
) -> None:
    _shell, manager = (
        _make_window_manager(
            qtbot
        )
    )

    assert not manager.close_window(
        "missing"
    )