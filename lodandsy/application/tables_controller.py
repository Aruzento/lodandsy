"""Standalone and embedded Table views. No knowledge of Cards/Maps/Dice widgets."""

from weakref import WeakSet

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QInputDialog
from shiboken6 import isValid

from lodandsy.ui.table_widget import TableWidget


class TablesController(QObject):
    def __init__(self, window, windows, service, open_entity=None):
        super().__init__(window)
        self.window, self.windows, self.service = window, windows, service
        self.open_entity = open_entity
        self._views = {}
        self._ui = {}
        service.table_changed.connect(self._refresh)
        service.table_deleted.connect(self._deleted)
        service.draft_changed.connect(self._draft_changed)
        service.projections_changed.connect(self._projections_changed)
        service.core.replaced.connect(self.reset)

    def request_table(self, parent_id=None):
        title, ok = QInputDialog.getText(self.window, "Новая таблица", "Название:")
        if ok and title.strip():
            self.open_table(self.service.create_table(title, parent_id).id)

    def open_table(self, key):
        document = self.service.get_table(key)
        existing = self.windows.find_window(f"table:{key}")
        if existing:
            return self.windows.focus_window(f"table:{key}")
        window = self.windows.open_window(
            f"table:{key}", document.title, lambda: self.table_view(key)
        )
        window.widget().restore_ui(self._ui.get(key, {}))
        window.closed.connect(lambda closed: self._ui.update({key: closed.widget().ui_state()}))
        return window

    def table_view(self, key):
        widget = TableWidget(
            self.service.get_table(key),
            self.service.drafts(key),
            service=self.service,
            open_entity=self.open_entity,
        )
        self.service.track_references(key)
        widget.setProperty("table_id", key)
        self._views.setdefault(key, WeakSet()).add(widget)
        widget.draft_changed.connect(lambda: self.service.notify_drafts(key))
        return widget

    def _projections_changed(self, key, cells):
        for widget in tuple(self._views.get(key, ())):
            if isValid(widget):
                widget.refresh_references(cells)

    def embedded_view(self, key, parent_id, previous=None):
        if key is None:
            return None
        try:
            entity = self.service.core.entities.get(key)
            if entity.kind != "table" or entity.parent_id != parent_id:
                return None
            if previous is not None and isValid(previous) and previous.property("table_id") == key:
                return previous
            return self.table_view(key)
        except ValueError:
            return None

    def _refresh(self, key, change):
        document = self.service.get_table(key)
        window = self.windows.find_window(f"table:{key}")
        if window:
            window.setWindowTitle(document.title)
        for widget in tuple(self._views.get(key, ())):
            if isValid(widget):
                widget.set_document(document)

    def _draft_changed(self, key, cells):
        for widget in tuple(self._views.get(key, ())):
            if not isValid(widget):
                continue
            widget.update_draft_notice()
            rows = {r.id: i for i, r in enumerate(widget.model.document.rows)}
            cols = {c.id: i for i, c in enumerate(widget.model.document.columns)}
            for row, col in cells:
                if row in rows and col in cols:
                    index = widget.model.index(rows[row], cols[col])
                    widget.model.dataChanged.emit(index, index)

    def discard_drafts(self, key):
        for widget in tuple(self._views.get(key, ())):
            if isValid(widget):
                widget.revert_active_editor()
        self.service.discard_drafts(key)

    def show_orphan_drafts(self):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout

        dialog = QDialog(self.window)
        dialog.setWindowTitle("Черновик удалённой ячейки")
        dialog.resize(560, 340)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            "\n\n".join(
                error + "\n" + str(key) + "\n" + raw
                for key, raw, error in self.service.orphan_drafts
            )
        )
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _deleted(self, key):
        self.windows.close_window(f"table:{key}")
        self._ui.pop(key, None)
        self._views.pop(key, None)

    def capture_ui(self):
        return {
            **self._ui,
            **{
                key: self.windows.find_window(f"table:{key}").widget().ui_state()
                for key in self.service.tables
                if self.windows.find_window(f"table:{key}")
            },
        }

    def restore_ui(self, values):
        self._ui = {
            key: value
            for key, value in values.items()
            if key in self.service.tables and isinstance(value, dict)
        }
        for key, value in self._ui.items():
            window = self.windows.find_window(f"table:{key}")
            if window:
                window.widget().restore_ui(value)

    def reset(self):
        self._views.clear()
        self._ui.clear()
