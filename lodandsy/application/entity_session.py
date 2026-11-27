"""Shared entity lifecycle and transaction notifications; no feature payload knowledge."""

import logging
from contextlib import contextmanager
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from lodandsy.domain.entity import ChangeSet, EntityCollection

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CommittedChange:
    generation: int
    serial: int
    changes: ChangeSet | None


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
        self._publishing = False
        self._pending_notifications = []
        self._dirty = False
        self.serial = 0
        self.last_commit = None
        self.prepare = None

    @property
    def in_transaction(self):
        return self._depth > 0

    @contextmanager
    def transaction(self):
        start, dirty = len(self._notifications), self._dirty
        self._depth += 1
        try:
            with self.entities.atomic():
                yield
                if self._depth == 1:
                    if self.prepare is not None:
                        self.prepare(self.entities.pending_changes())
                    changes = self.entities.pending_changes()
        except BaseException:
            del self._notifications[start:]
            self._dirty = dirty
            raise
        finally:
            self._depth -= 1
        if self._depth == 0:
            notifications, self._notifications = self._notifications, []
            changed, self._dirty = self._dirty, False
            self._publish(notifications, changed or bool(changes), changes)

    def _publish(self, notifications, changed, changes=None):
        if changed:
            self.serial += 1
            self.last_commit = CommittedChange(self.generation, self.serial, changes)
        self._pending_notifications.extend(
            (self.generation, callback) for callback in notifications
        )
        if self._publishing:
            if changed:
                self.committed.emit()
            return
        self._publishing = True
        try:
            # Saving must observe the committed revision even if a callback opens
            # a nested event loop, commits again or raises after the rollback boundary.
            if changed:
                self.committed.emit()
            while self._pending_notifications:
                pending, self._pending_notifications = self._pending_notifications, []
                for generation, callback in pending:
                    if generation != self.generation:
                        continue
                    try:
                        callback()
                    except Exception:
                        logger.exception("Post-commit entity notification failed")
        finally:
            self._publishing = False

    def after_commit(self, callback):
        if self._depth:
            self._notifications.append(callback)
        else:
            callback()

    def mark_changed(self):
        if self._depth:
            self._dirty = True
        else:
            self._publish((), True)

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
        if self.in_transaction:
            raise ValueError("Нельзя заменить проект внутри транзакции")
        self.generation += 1
        self.last_commit = None
        self.entities = entities
        self.select(None)
        self.replaced.emit()
