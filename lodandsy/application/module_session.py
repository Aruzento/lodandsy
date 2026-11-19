import math
from dataclasses import replace
from types import MappingProxyType

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from lodandsy.domain.document_payloads import module_document, module_payload, project_entities
from lodandsy.domain.map_document import (
    MapDocument,
    MapLayer,
    PlacedAssetObject,
    TokenInstance,
)
from lodandsy.domain.table_document import TableDocument


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
    replaced = Signal()

    def __init__(self, parent=None, *, entities=None, delete_handler=None):
        super().__init__(parent)
        self.entities = entities if entities is not None else project_entities()
        self.delete_handler = delete_handler
        self._undo = {}
        self._deleted_card_ids = set()

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

    def reset(self, maps=(), tables=(), *, entities=None):
        replacement = (
            entities if entities is not None else project_entities(maps=maps, tables=tables)
        )
        for stack in self._undo.values():
            stack.deleteLater()
        self._undo.clear()
        self._deleted_card_ids.clear()
        self.entities = replacement
        self.replaced.emit()

    def _put(self, document):
        self.entities.update(document.id, title=document.title)
        self.entities.put_payload(document.id, module_payload(document))
        self.entities.project(document.id, lambda entity, payload: document)

    def _get(self, key, kind):
        if self.entities.get(key).kind != kind:
            raise ValueError("Неподдерживаемый тип документа")
        return module_document(self.entities, key)

    def _delete(self, key):
        if self.delete_handler is not None:
            return self.delete_handler(key)
        deleted = self.entities.delete(key)
        self.notify_deleted(deleted)
        return deleted

    def plan_delete(self, deleted):
        return {
            document.id: module_payload(
                replace(
                    document,
                    tokens=tuple(
                        token for token in document.tokens if token.card_id not in deleted
                    ),
                )
            )
            for document in self.maps.values()
            if document.id not in deleted
            and any(token.card_id in deleted for token in document.tokens)
        }

    def placement_count(self, ids):
        return sum(t.card_id in ids for d in self.maps.values() for t in d.tokens)

    def card(self, key):
        from lodandsy.domain.card_collection import CardCollection

        return CardCollection(entities=self.entities).get(key)

    def notify_deleted(self, deleted):
        self._deleted_card_ids.update(deleted)
        for key in deleted:
            stack = self._undo.pop(key, None)
            if stack is not None:
                stack.clear()
                stack.deleteLater()
            # Each listener closes only its own key. Payloads were removed atomically.
            self.map_deleted.emit(key)
            self.table_deleted.emit(key)
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
        tokens = []
        for token in document.tokens:
            if token.card_id in self._deleted_card_ids:
                try:
                    self.card(token.card_id)
                except ValueError:
                    continue
            tokens.append(token)
        document = replace(document, tokens=tuple(tokens))
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
        if changes.keys() - {"title", "tokens", "grid", "layers", "objects"}:
            raise ValueError("Изменять ID или источник карты этой командой нельзя")
        before = self.get_map(map_id)
        after = replace(before, **changes)
        if before != after:
            self.undo_stack(map_id).push(MapEdit(self, before, after, command))

    def add_token(self, map_id, card_id, x, y, **values):
        self.card(card_id)
        document = self.get_map(map_id)
        token = TokenInstance(card_id, x, y, **values)
        self.edit_map(map_id, tokens=(*document.tokens, token), command="Разместить карточку")
        return token

    def add_card_placement(self, card, map_id, x, y):
        before = self.get_map(map_id)
        token = TokenInstance(card.id, x, y)
        after = replace(before, tokens=(*before.tokens, token))
        with self.entities.atomic():
            self.entities.create("card", card.title, card.payload(), card.parent_id, id=card.id)
            self.entities.put_payload(map_id, module_payload(after))
        self.undo_stack(map_id).push(MapEdit(self, before, after, "Разместить новую карточку"))
        return token

    def edit_token(self, map_id, token_id, **changes):
        if changes.keys() - {
            "x",
            "y",
            "cells_w",
            "cells_h",
            "kind_override",
            "z",
            "label_override",
            "image_override",
            "layer_id",
        }:
            raise ValueError("Неподдерживаемые поля размещения")
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

    def add_layer(self, map_id, title):
        document = self.get_map(map_id)
        layer = MapLayer(title, position=len(document.layers))
        self.edit_map(map_id, layers=(*document.layers, layer), command="Создать слой")
        return layer

    def edit_layer(self, map_id, layer_id, **changes):
        if changes.keys() - {"title", "visible"}:
            raise ValueError("Неподдерживаемые свойства слоя")
        document = self.get_map(map_id)
        if not any(layer.id == layer_id for layer in document.layers):
            raise ValueError("Слой отсутствует")
        self.edit_map(
            map_id,
            layers=tuple(
                replace(layer, **changes) if layer.id == layer_id else layer
                for layer in document.layers
            ),
            command="Изменить слой",
        )

    def move_layer(self, map_id, layer_id, position):
        document = self.get_map(map_id)
        layers = sorted(document.layers, key=lambda layer: layer.position)
        if type(position) is not int or not 0 <= position < len(layers):
            raise ValueError("Некорректная позиция слоя")
        layer = next(layer for layer in layers if layer.id == layer_id)
        layers.remove(layer)
        layers.insert(position, layer)
        self.edit_map(
            map_id,
            layers=tuple(replace(layer, position=i) for i, layer in enumerate(layers)),
            command="Переместить слой",
        )

    def delete_layer(self, map_id, layer_id, *, delete_contents=False):
        document = self.get_map(map_id)
        if not any(layer.id == layer_id for layer in document.layers):
            raise ValueError("Слой отсутствует")
        nonempty = any(o.layer_id == layer_id for o in (*document.objects, *document.tokens))
        if nonempty and not delete_contents:
            raise ValueError("Слой содержит объекты; подтвердите удаление содержимого")
        layers = sorted(
            (layer for layer in document.layers if layer.id != layer_id),
            key=lambda layer: layer.position,
        )
        self.edit_map(
            map_id,
            layers=tuple(replace(layer, position=i) for i, layer in enumerate(layers)),
            objects=tuple(o for o in document.objects if o.layer_id != layer_id),
            tokens=tuple(t for t in document.tokens if t.layer_id != layer_id),
            command="Удалить слой",
        )

    def add_object(self, map_id, layer_id, asset_id, x, y, width=128, height=128):
        document = self.get_map(map_id)
        item = PlacedAssetObject(layer_id, asset_id, x, y, width, height)
        self.edit_map(map_id, objects=(*document.objects, item), command="Разместить изображение")
        return item

    def edit_object(self, map_id, object_id, **changes):
        if changes.keys() - {"x", "y", "width", "height", "rotation", "z", "layer_id"}:
            raise ValueError("Неподдерживаемые свойства объекта")
        document = self.get_map(map_id)
        if not any(o.id == object_id for o in document.objects):
            raise ValueError("Объект отсутствует")
        self.edit_map(
            map_id,
            objects=tuple(
                replace(o, **changes) if o.id == object_id else o for o in document.objects
            ),
            command="Изменить объект",
        )

    def delete_object(self, map_id, object_id):
        document = self.get_map(map_id)
        if not any(o.id == object_id for o in document.objects):
            raise ValueError("Объект отсутствует")
        self.edit_map(
            map_id,
            objects=tuple(o for o in document.objects if o.id != object_id),
            command="Удалить объект",
        )

    def delete_map(self, map_id):
        self.get_map(map_id)
        return self._delete(map_id)

    def create_table(self, title, parent_id=None):
        table = TableDocument(title)
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
            self.update_table(after)

    def update_table(self, document):
        if not isinstance(document, TableDocument):
            raise ValueError("Ожидается валидированная таблица")
        before = self.get_table(document.id)
        if before != document:
            self._put(document)
            self.table_changed.emit(document.id)
            self.changed.emit()

    def delete_table(self, table_id):
        self.get_table(table_id)
        return self._delete(table_id)
