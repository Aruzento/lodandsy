from dataclasses import replace
from types import MappingProxyType

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from lodandsy.domain.map_document import MapDocument, MapPin
from lodandsy.domain.tools import RandomTable


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
    map_deleted = Signal(str)
    table_deleted = Signal(str)
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._maps = {}
        self._tables = {}
        self._undo = {}

    @property
    def maps(self):
        return MappingProxyType(self._maps)

    @property
    def tables(self):
        return MappingProxyType(self._tables)

    def reset(self, maps=(), tables=()):
        for stack in self._undo.values():
            stack.deleteLater()
        self._undo.clear()
        maps, tables = tuple(maps), tuple(tables)
        ids = [item.id for item in (*maps, *tables)]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate module entity ID")
        self._maps = {item.id: item for item in maps}
        self._tables = {item.id: item for item in tables}

    def undo_stack(self, map_id):
        self.get_map(map_id)
        if map_id not in self._undo:
            self._undo[map_id] = QUndoStack(self)
            self._undo[map_id].setUndoLimit(200)
        return self._undo[map_id]

    def get_map(self, map_id):
        if map_id not in self.maps:
            raise ValueError("Карта отсутствует")
        return self.maps[map_id]

    def get_table(self, table_id):
        if table_id not in self.tables:
            raise ValueError("Таблица отсутствует")
        return self.tables[table_id]

    def _put_map(self, document):
        self._maps[document.id] = document
        self.map_changed.emit(document.id)
        self.changed.emit()

    def create_map(self, title, asset_id):
        document = MapDocument(title, asset_id)
        self._put_map(document)
        return document

    def edit_map(self, map_id, *, command="Изменить карту", **changes):
        before = self.get_map(map_id)
        after = replace(before, **changes)
        if before != after:
            self.undo_stack(map_id).push(MapEdit(self, before, after, command))

    def add_pin(self, map_id, title, x, y, card_id=None):
        pin = MapPin(title, x, y, card_id=card_id)
        self.edit_map(map_id, pins=(*self.get_map(map_id).pins, pin), command="Добавить маркер")
        return pin

    def edit_pin(self, map_id, pin_id, **changes):
        document = self.get_map(map_id)
        if pin_id not in {p.id for p in document.pins}:
            raise ValueError("Маркер отсутствует")
        pins = tuple(replace(pin, **changes) if pin.id == pin_id else pin for pin in document.pins)
        self.edit_map(map_id, pins=pins, command="Изменить маркер")

    def delete_pin(self, map_id, pin_id):
        document = self.get_map(map_id)
        self.edit_map(map_id, pins=tuple(p for p in document.pins if p.id != pin_id),
                      command="Удалить маркер")

    def delete_map(self, map_id):
        self.get_map(map_id)
        self._maps.pop(map_id)
        stack = self._undo.pop(map_id, None)
        if stack is not None:
            stack.deleteLater()
        self.map_deleted.emit(map_id)
        self.changed.emit()

    def create_table(self, title):
        table = RandomTable(title)
        self._tables[table.id] = table
        self.table_changed.emit(table.id)
        self.changed.emit()
        return table

    def edit_table(self, table_id, **changes):
        before = self.get_table(table_id)
        after = replace(before, **changes)
        if after != before:
            self._tables[table_id] = after
            self.table_changed.emit(table_id)
            self.changed.emit()

    def delete_table(self, table_id):
        self.get_table(table_id)
        self._tables.pop(table_id)
        self.table_deleted.emit(table_id)
        self.changed.emit()
