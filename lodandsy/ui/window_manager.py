from collections.abc import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QWidget

from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.workspace_placement import WorkspacePlacement


class WorkspaceWindow(QObject):
    closed = Signal(object)

    def __init__(self, key, dock, parent):
        super().__init__(parent)
        self.key, self.dock = key, dock

    def widget(self):
        return self.dock.widget()

    def windowTitle(self):
        return self.dock.windowTitle()

    def setWindowTitle(self, title):
        self.dock.setWindowTitle(title)

    def close(self):
        self.dock.closeDockWidget()
        return True


class WindowManager(QObject):
    active_window_changed = Signal(object)

    def __init__(self, shell: AppShell):
        super().__init__(shell)
        self.workspace = shell.workspace
        self._windows: dict[str, WorkspaceWindow] = {}
        self._active_window_key: str | None = None
        QApplication.instance().focusChanged.connect(self._on_focus_changed)

    @property
    def active_window_key(self):
        return self._active_window_key

    def _set_active_window(self, key):
        if self._active_window_key != key:
            self._active_window_key = key
            self.active_window_changed.emit(key)

    def _on_focus_changed(self, _old, current):
        if current is not None:
            for key, window in self._windows.items():
                if current is window.dock or window.dock.isAncestorOf(current):
                    self._set_active_window(key)
                    return

    def open_window(self, key: str, title: str, content_factory: Callable[[], QWidget],
                    placement=WorkspacePlacement.CENTER):
        existing = self.find_window(key)
        if existing is not None:
            self.focus_window(key)
            return existing
        content = content_factory()
        if not isinstance(content, QWidget):
            raise TypeError("content_factory must return QWidget")
        dock = self.workspace.create_document(key, title, content)
        window = WorkspaceWindow(key, dock, self)
        anchor = self.find_window(self.active_window_key)
        self._windows[key] = window
        dock.closed.connect(lambda: self._on_window_closed(window))
        try:
            self.workspace.add_document(dock, placement, anchor.dock if anchor else None)
        except Exception:
            self._windows.pop(key, None)
            self.workspace.removeDockWidget(dock)
            dock.deleteLater()
            window.deleteLater()
            raise
        self.focus_window(key)
        return window

    def find_window(self, key):
        return self._windows.get(key)

    def focus_window(self, key):
        window = self.find_window(key)
        if window is not None:
            self.workspace.focus_document(window.dock)
            self._set_active_window(key)
        return window

    def close_window(self, key):
        window = self.find_window(key)
        if window is None:
            return False
        window.close()
        return key not in self._windows

    def window_keys(self):
        return tuple(self._windows)

    def _on_window_closed(self, window):
        if self._windows.get(window.key) is not window:
            return
        del self._windows[window.key]
        if self._active_window_key == window.key:
            self._set_active_window(None)
        window.closed.emit(window)
        self.workspace.removeDockWidget(window.dock)
        window.dock.deleteLater()
        window.deleteLater()
