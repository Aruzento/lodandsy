"""Semantic structured-field buffers with optimistic conflict detection; no widget references."""

from dataclasses import dataclass, replace
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from lodandsy.application.edit_conflict import EditConflict


@dataclass(slots=True)
class FieldEdit:
    key: tuple
    base: object
    raw: str
    committed_text: str
    initial_draft: object = None
    draft_version: object = None
    initial_status: tuple = ()


def value_text(value):
    return (
        ""
        if value is None
        else ", ".join(map(str, value))
        if isinstance(value, tuple)
        else str(value)
    )


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
        self.conflicts = {}
        self._draft_bases = {}
        self._draft_versions = {}
        self.format_value = lambda key, value: value_text(value)

    def _draft(self, key, raw, *, edit=None):
        version = self._draft_versions[key] = object()
        if edit is not None:
            edit.draft_version = version
        if raw is None:
            self.conflicts.pop(key, None)
            self._draft_bases.pop(key, None)
            self.errors.pop(key, None)
        if self.on_draft:
            self.on_draft(key, raw)
        elif raw is None:
            self.drafts.pop(key, None)
        else:
            self.drafts[key] = raw
        self.changed.emit(key)

    def begin(self, key):
        value = self.read(key)
        raw = self.drafts.get(key, self.format_value(key, value))
        owner = str(uuid4())
        conflict = self.conflicts.get(key)
        self._edits[owner] = FieldEdit(
            key,
            self._draft_bases.get(key, value),
            raw,
            raw,
            self.drafts.get(key),
            self._draft_versions.get(key),
            (
                self.errors.get(key),
                self._draft_bases.get(key, value),
                replace(conflict) if conflict else None,
            ),
        )
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
                if edit.key in self.conflicts:
                    self.conflicts[edit.key].raw = edit.raw
                    raise ValueError(
                        "Конфликт: выберите «Использовать сохранённое» или «Применить мой вариант»"
                    )
                value = self.parse(edit.key, edit.raw)
                current = self.read(edit.key)
                if current != edit.base and current != value:
                    self.conflicts[edit.key] = EditConflict(edit.raw, edit.base, current)
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
                self._draft(edit.key, None, edit=edit)
            except ValueError as error:
                self._draft_bases.setdefault(edit.key, edit.base)
                self.errors[edit.key] = str(error)
                self._draft(edit.key, edit.raw, edit=edit)
                success = False
        if finish:
            self._edits.pop(owner, None)
        self.pending_changed.emit()
        return success

    def resolve(self, key, *, mine=False):
        conflict = self.conflicts.get(key)
        if mine:
            if conflict is None:
                return False
            current = self.read(key)
            if current != conflict.observed:
                conflict.observed = current
                self.errors[key] = "Сохранённое значение снова изменилось: " + value_text(current)
                self._draft(key, self.drafts[key])
                return False
            try:
                value = self.parse(key, self.drafts[key])
                if value != current:
                    self.write(key, value)
            except ValueError as error:
                self.errors[key] = str(error)
                self._draft(key, self.drafts[key])
                return False
        for owner, edit in tuple(self._edits.items()):
            if edit.key == key:
                self._edits.pop(owner)
        self.errors.pop(key, None)
        self._draft(key, None)
        self.pending_changed.emit()
        return True

    def cancel(self, owner):
        edit = self._edits.pop(owner, None)
        if edit is not None and self._draft_versions.get(edit.key) is edit.draft_version:
            # Escape restores only this edit's publication, never a newer owner's draft.
            if edit.initial_draft is not None:
                error, base, conflict = edit.initial_status
                self._draft_bases[edit.key] = base  # None is also a canonical baseline.
                for state, value in ((self.errors, error), (self.conflicts, conflict)):
                    if value is None:
                        state.pop(edit.key, None)
                    else:
                        state[edit.key] = value
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
        for key in self.conflicts.keys() | self._draft_bases.keys() | self._draft_versions.keys():
            if ids is None or key[0] in ids:
                self.conflicts.pop(key, None)
                self._draft_bases.pop(key, None)
                self._draft_versions.pop(key, None)
        for key in tuple(self.errors):
            if ids is None or key[0] in ids:
                self.errors.pop(key, None)
        self.pending_changed.emit()

    def discard(self, ids=None):
        self.clear(ids)
        for key in tuple(self.drafts):
            if ids is None or key[0] in ids:
                self._draft(key, None)

    def discard_keys(self, keys):
        keys = set(keys)
        for owner, edit in tuple(self._edits.items()):
            if edit.key in keys:
                self._edits.pop(owner)
        for key in keys:
            self._draft(key, None)
        self.pending_changed.emit()

    @property
    def keys(self):
        return (
            {edit.key for edit in self._edits.values()}
            | self.drafts.keys()
            | self.errors.keys()
            | self.conflicts.keys()
        )

    def remove_entities(self, ids):
        self.clear(set(ids))
        for key in tuple(self.drafts):
            if key[0] in ids:
                self._draft(key, None)
