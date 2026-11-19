import math
from dataclasses import replace
from types import MappingProxyType

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from lodandsy.domain.dice_document import DiceDocument
from lodandsy.domain.document_payloads import module_document, module_payload, project_entities
from lodandsy.domain.map_document import MapDocument, MapToken
from lodandsy.domain.table_document import RandomTable


class MapEdit(QUndoCommand):
    def __init__(self, session, before, after, title):
        super().__init__(title)
        self.session, self.before, self.after = session, before, after

    def undo(self):
        self.session._put_map(self.before)

    def redo(self):
        self.session._put_map(self.after)


class ModuleSession(QObject):
    """Canonical in-memory state of the two built-in modules; no SQL or widgets."""

    map_changed = Signal(str)
    table_changed = Signal(str)
    dice_changed = Signal(str)
    dice_deleted = Signal(str)
    map_deleted = Signal(str)
    table_deleted = Signal(str)
    changed = Signal()
    replaced = Signal()

    def __init__(self, parent=None, *, entities=None, delete_handler=None):
        super().__init__(parent)
        self.entities = entities if entities is not None else project_entities()
        self.delete_handler = delete_handler
        self._undo = {}

    def _documents(self, kind):
        return MappingProxyType(
            {
                e.id: module_document(self.entities, e.id)
                for e in self.entities.summaries()
                if e.kind == kind
            }
        )

    @property
    def maps(self):
        return self._documents("map")

    @property
    def tables(self):
        return self._documents("table")

    @property
    def dice(self):
        return self._documents("dice")

    def reset(self, maps=(), tables=(), dice=(), *, entities=None):
        replacement = (
            entities
            if entities is not None
            else project_entities(maps=maps, tables=tables, dice=dice)
        )
        for stack in self._undo.values():
            stack.deleteLater()
        self._undo.clear()
        self.entities = replacement
        self.replaced.emit()

    def _put(self, document):
        self.entities.update(document.id, title=document.title)
        self.entities.put_payload(document.id, module_payload(document))

    def _get(self, key, kind):
        if self.entities.get(key).kind != kind:
            raise ValueError("Неподдерживаемый тип документа")
        return module_document(self.entities, key)

    def get_dice(self, key):
        return self._get(key, "dice")

    def create_dice(self, title, parent_id=None):
        document = DiceDocument(title)
        self.entities.create(
            "dice", document.title, module_payload(document), parent_id, id=document.id
        )
        self.dice_changed.emit(document.id)
        self.changed.emit()
        return document

    def edit_dice(self, key, **changes):
        if changes.keys() - {"title", "presets"}:
            raise ValueError("Неподдерживаемые поля кубиков")
        before = self.get_dice(key)
        after = replace(before, **changes)
        if before != after:
            self._put(after)
            self.dice_changed.emit(key)
            self.changed.emit()

    def _delete(self, key):
        if self.delete_handler is not None:
            return self.delete_handler(key)
        deleted = self.entities.delete(key)
        self.notify_deleted(deleted)
        return deleted

    def notify_deleted(self, deleted):
        for key in deleted:
            stack = self._undo.pop(key, None)
            if stack is not None:
                stack.clear()
                stack.deleteLater()
            # Each listener closes only its own key. Payloads were removed atomically.
            self.map_deleted.emit(key)
            self.table_deleted.emit(key)
            self.dice_deleted.emit(key)
        self.changed.emit()

    def undo_stack(self, map_id):
        self.get_map(map_id)
        if map_id not in self._undo:
            self._undo[map_id] = QUndoStack(self)
            self._undo[map_id].setUndoLimit(200)
        return self._undo[map_id]

    def get_map(self, map_id):
        return self._get(map_id, "map")

    def get_table(self, table_id):
        return self._get(table_id, "table")

    def _put_map(self, document):
        self._put(document)
        self.map_changed.emit(document.id)
        self.changed.emit()

    def create_map(self, title, asset_id, parent_id=None):
        document = MapDocument(title, asset_id)
        self.entities.create(
            "map", document.title, module_payload(document), parent_id, id=document.id
        )
        self.map_changed.emit(document.id)
        self.changed.emit()
        return document

    def edit_map(self, map_id, *, command="Изменить карту", **changes):
        if changes.keys() - {"title", "tokens", "grid"}:
            raise ValueError("Изменять ID или источник карты этой командой нельзя")
        before = self.get_map(map_id)
        after = replace(before, **changes)
        if before != after:
            self.undo_stack(map_id).push(MapEdit(self, before, after, command))

    def add_token(self, map_id, title, asset_id, x, y, **values):
        token = MapToken(title, asset_id, x, y, **values)
        self.edit_map(
            map_id, tokens=(*self.get_map(map_id).tokens, token), command="Добавить токен"
        )
        return token

    def edit_token(self, map_id, token_id, **changes):
        if changes.keys() - {
            "title",
            "asset_id",
            "x",
            "y",
            "cells_w",
            "cells_h",
            "kind",
            "z",
            "entity_id",
        }:
            raise ValueError("Неподдерживаемые поля токена")
        document = self.get_map(map_id)
        if token_id not in {token.id for token in document.tokens}:
            raise ValueError("Токен отсутствует")
        tokens = tuple(
            replace(token, **changes) if token.id == token_id else token
            for token in document.tokens
        )
        self.edit_map(map_id, tokens=tokens, command="Изменить токен")

    def move_token(self, map_id, token_id, x, y, *, bounds=None):
        if any(
            type(value) not in (int, float) or not -1e9 <= value <= 1e9 or not math.isfinite(value)
            for value in (x, y)
        ):
            raise ValueError("Некорректные координаты токена")
        document = self.get_map(map_id)
        token = next((t for t in document.tokens if t.id == token_id), None)
        if token is None:
            raise ValueError("Токен отсутствует")
        grid = document.grid
        if grid.snap:
            x, y = grid.snap_point(x, y, token.cells_w, token.cells_h)
        if bounds is not None:
            x, y = max(0, min(bounds[0], x)), max(0, min(bounds[1], y))
        self.edit_token(map_id, token_id, x=x, y=y)

    def delete_token(self, map_id, token_id):
        document = self.get_map(map_id)
        if token_id not in {token.id for token in document.tokens}:
            raise ValueError("Токен отсутствует")
        self.edit_map(
            map_id,
            tokens=tuple(token for token in document.tokens if token.id != token_id),
            command="Удалить токен",
        )

    def delete_map(self, map_id):
        self.get_map(map_id)
        return self._delete(map_id)

    def create_table(self, title, parent_id=None):
        table = RandomTable(title)
        self.entities.create("table", table.title, module_payload(table), parent_id, id=table.id)
        self.table_changed.emit(table.id)
        self.changed.emit()
        return table

    def edit_table(self, table_id, **changes):
        if changes.keys() - {"title", "columns", "rows"}:
            raise ValueError("Неподдерживаемые поля таблицы")
        before = self.get_table(table_id)
        after = replace(before, **changes)
        if after != before:
            self._put(after)
            self.table_changed.emit(table_id)
            self.changed.emit()

    def delete_table(self, table_id):
        self.get_table(table_id)
        return self._delete(table_id)
