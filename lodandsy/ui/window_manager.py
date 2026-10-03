from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.workspace_dock import WorkspaceDock
from lodandsy.ui.workspace_placement import (
    WorkspacePlacement,
)


class WindowManager:
    def __init__(
        self,
        shell: AppShell,
    ) -> None:
        self._shell = shell

        self._windows: dict[
            str,
            WorkspaceDock,
        ] = {}

    def open_window(
        self,
        key: str,
        title: str,
        content_factory: Callable[[], QWidget],
        placement: WorkspacePlacement = (
            WorkspacePlacement.LEFT
        ),
    ) -> WorkspaceDock:
        existing = self.find_window(
            key
        )

        if existing is not None:
            self.focus_window(
                key
            )
            return existing

        content = content_factory()

        if not isinstance(
            content,
            QWidget,
        ):
            raise TypeError(
                "content_factory must return QWidget"
            )

        dock = WorkspaceDock(
            key=key,
            title=title,
            content=content,
            parent=self._shell,
        )

        self._windows[key] = dock

        dock.closed.connect(
            self._on_window_closed
        )

        try:
            self._shell.add_workspace_dock(
                dock,
                placement,
            )
        except Exception:
            self._windows.pop(
                key,
                None,
            )

            dock.deleteLater()

            raise

        return dock

    def find_window(
        self,
        key: str,
    ) -> WorkspaceDock | None:
        return self._windows.get(
            key
        )

    def focus_window(
        self,
        key: str,
    ) -> WorkspaceDock | None:
        dock = self.find_window(
            key
        )

        if dock is None:
            return None

        if dock.isMinimized():
            window_state = (
                dock.windowState()
            )

            window_state &= (
                ~Qt.WindowState.WindowMinimized
            )

            window_state |= (
                Qt.WindowState.WindowActive
            )

            dock.setWindowState(
                window_state
            )

        dock.show()
        dock.raise_()

        if dock.isFloating():
            dock.activateWindow()
        else:
            self._shell.show()
            self._shell.raise_()
            self._shell.activateWindow()

            dock.raise_()

        return dock

    def close_window(
        self,
        key: str,
    ) -> bool:
        dock = self.find_window(
            key
        )

        if dock is None:
            return False

        return dock.close()

    def window_keys(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            self._windows
        )

    def _on_window_closed(
        self,
        dock: object,
    ) -> None:
        if not isinstance(
            dock,
            WorkspaceDock,
        ):
            return

        current = self._windows.get(
            dock.key
        )

        if current is not dock:
            return

        self._windows.pop(
            dock.key,
            None,
        )

        self._shell.remove_workspace_dock(
            dock
        )

        dock.deleteLater()