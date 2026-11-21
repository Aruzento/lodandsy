"""Shared entity lifecycle and transaction notifications; no feature payload knowledge."""

from contextlib import contextmanager

from PySide6.QtCore import QObject, Signal

from lodandsy.domain.entity import EntityCollection


class EntitySession(QObject):
    entity_created = Signal(str)
    entity_changed = Signal(str, object)
    entities_deleted = Signal(object)
    replaced = Signal()
    selection_changed = Signal(object)
    committed = Signal()

    def __init__(self, entities=None, parent=None):
        super().__init__(parent)
        self.entities = entities if entities is not None else EntityCollection()
        self.selected_id = None
        self.generation = 0
        self._depth = 0
        self._notifications = []
        self._dirty = False
        self.serial = 0
        self.prepare = None

    @contextmanager
    def transaction(self):
        start, dirty = len(self._notifications), self._dirty
        before_payloads = (
            {e.id: self.entities.payload(e.id) for e in self.entities.summaries()}
            if self._depth == 0
            else None
        )
        self._depth += 1
        try:
            with self.entities.atomic():
                yield
                if self._depth == 1 and self.prepare is not None:
                    self.prepare(before_payloads)
        except Exception:
            del self._notifications[start:]
            self._dirty = dirty
            raise
        finally:
            self._depth -= 1
        if self._depth == 0:
            notifications, self._notifications = self._notifications, []
            changed, self._dirty = self._dirty, False
            for callback in notifications:
                callback()
            if changed:
                self.serial += 1
                self.committed.emit()

    def after_commit(self, callback):
        if self._depth:
            self._notifications.append(callback)
        else:
            callback()

    def mark_changed(self):
        if self._depth:
            self._dirty = True
        else:
            self.serial += 1
            self.committed.emit()

    def select(self, key):
        if key is not None:
            self.entities.get(key)
        if self.selected_id != key:
            self.selected_id = key
            self.selection_changed.emit(key)

    def update(self, key, **changes):
        before = self.entities.get(key)
        with self.transaction():
            after = self.entities.update(key, **changes)
            fields = frozenset(
                k
                for k in ("title", "parent_id", "position")
                if getattr(before, k) != getattr(after, k)
            )
            if fields:
                self.after_commit(lambda: self.entity_changed.emit(key, fields))
                self.mark_changed()
        return after

    def delete(self, key, payload_changes=None):
        with self.transaction():
            for identity, payload in (payload_changes or {}).items():
                self.entities.put_payload(identity, payload)
            deleted = self.entities.delete(key)
            if self.selected_id in deleted:
                self.after_commit(lambda: self.select(None))
            self.after_commit(lambda: self.entities_deleted.emit(deleted))
            for identity in payload_changes or {}:
                self.after_commit(
                    lambda key=identity: self.entity_changed.emit(key, frozenset({"payload"}))
                )
            self.mark_changed()
        return deleted

    def replace(self, entities):
        self.generation += 1
        self.select(None)
        self.entities = entities
        self.replaced.emit()
