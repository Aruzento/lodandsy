"""Semantic structured-field buffers with optimistic conflict detection; no widget references."""

from dataclasses import dataclass
from uuid import uuid4

from PySide6.QtCore import QObject, Signal


@dataclass(slots=True)
class FieldEdit:
    key: tuple
    base: object
    raw: str
    committed_text: str
    initial_draft: object = None


def value_text(value):
    return "" if value is None else ", ".join(value) if isinstance(value, tuple) else str(value)


class FieldEdits(QObject):
    changed = Signal(object)
    pending_changed = Signal()

    def __init__(self, read, write, parse, drafts, parent=None, on_draft=None):
        super().__init__(parent)
        self.read, self.write, self.parse, self.drafts, self.on_draft = (
            read,
            write,
            parse,
            drafts,
            on_draft,
        )
        self._edits = {}
        self.errors = {}

    def _draft(self, key, raw):
        if self.on_draft:
            self.on_draft(key, raw)
        elif raw is None:
            self.drafts.pop(key, None)
        else:
            self.drafts[key] = raw
        self.changed.emit(key)

    def begin(self, key):
        value = self.read(key)
        raw = self.drafts.get(key, value_text(value))
        owner = str(uuid4())
        self._edits[owner] = FieldEdit(key, value, raw, raw, self.drafts.get(key))
        return owner

    def has(self, owner):
        return owner in self._edits

    def has_key(self, key):
        return any(edit.key == key for edit in self._edits.values())

    def text(self, owner, raw):
        if owner in self._edits:
            self._edits[owner].raw = raw
            self.pending_changed.emit()

    def commit(self, owner, *, finish=False):
        edit = self._edits.get(owner)
        if edit is None:
            return True
        success = True
        if edit.raw != edit.committed_text or edit.initial_draft is not None:
            try:
                value = self.parse(edit.key, edit.raw)
                current = self.read(edit.key)
                if current != edit.base and current != value:
                    raise ValueError(
                        "Поле изменено в другом представлении. Текущее значение: "
                        + value_text(current)
                    )
                if current != value:
                    self.write(edit.key, value)
                edit.base = self.read(edit.key)
                edit.committed_text = edit.raw
                edit.initial_draft = None
                self.errors.pop(edit.key, None)
                self._draft(edit.key, None)
            except ValueError as error:
                self.errors[edit.key] = str(error)
                self._draft(edit.key, edit.raw)
                success = False
        if finish:
            self._edits.pop(owner, None)
        self.pending_changed.emit()
        return success

    def cancel(self, owner):
        edit = self._edits.pop(owner, None)
        if edit is not None:
            self._draft(edit.key, edit.initial_draft)
        self.pending_changed.emit()

    def flush(self):
        for owner in tuple(self._edits):
            self.commit(owner)

    @property
    def pending_count(self):
        return sum(edit.raw != edit.committed_text for edit in self._edits.values())

    def clear(self, ids=None):
        for owner, edit in tuple(self._edits.items()):
            if ids is None or edit.key[0] in ids:
                self._edits.pop(owner)
        for key in tuple(self.errors):
            if ids is None or key[0] in ids:
                self.errors.pop(key, None)
        self.pending_changed.emit()

    def discard(self, ids=None):
        self.clear(ids)
        for key in tuple(self.drafts):
            if ids is None or key[0] in ids:
                self._draft(key, None)

    def remove_entities(self, ids):
        self.clear(set(ids))
        for key in tuple(self.drafts):
            if key[0] in ids:
                self._draft(key, None)
