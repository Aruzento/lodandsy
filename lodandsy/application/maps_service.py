"""Map commands and one Undo history per map; no Table, Dice or feature editor dependency."""

import math
from dataclasses import replace
from types import MappingProxyType

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QUndoCommand, QUndoStack
from shiboken6 import isValid

from lodandsy.application.entity_session import EntitySession
from lodandsy.domain.map_document import (
    MapDocument,
    MapLayer,
    MapPayload,
    PlacedAssetObject,
    TokenInstance,
)


def map_payload(document):
    return MapPayload(
        document.asset_id,
        document.tokens,
        document.grid,
        document.layers,
        document.objects,
        document.layers_initialized,
        document.fog,
        document.shapes,
        document.portals,
    )


class GuardedUndoStack(QUndoStack):
    blocked = Signal(str)

    def undo(self):
        if not self.canUndo():
            return False
        try:
            self.command(self.index() - 1).check(False)
        except ValueError as error:
            self.blocked.emit(str(error))
            return False
        super().undo()
        return True

    def redo(self):
        if not self.canRedo():
            return False
        try:
            self.command(self.index()).check(True)
        except ValueError as error:
            self.blocked.emit(str(error))
            return False
        super().redo()
        return True

    def _action(self, parent, prefix, redo):
        action = QAction(parent)
        action.triggered.connect(self.redo if redo else self.undo)

        def update():
            if not isValid(self) or not isValid(action):
                return
            text = self.redoText() if redo else self.undoText()
            action.setText(prefix + (" · " + text if text else ""))
            action.setEnabled(self.canRedo() if redo else self.canUndo())

        self.indexChanged.connect(update)
        self.canUndoChanged.connect(update)
        self.canRedoChanged.connect(update)
        update()
        return action

    def createUndoAction(self, parent, prefix=""):
        return self._action(parent, prefix, False)

    def createRedoAction(self, parent, prefix=""):
        return self._action(parent, prefix, True)


class MapEdit(QUndoCommand):
    def __init__(self, session, before, after, title):
        super().__init__(title)
        self.session, self.before, self.after = session, before, after
        self.generation = session.core.generation
        self.fields = tuple(
            key
            for key in (
                "tokens",
                "grid",
                "layers",
                "objects",
                "layers_initialized",
                "fog",
                "shapes",
                "portals",
            )
            if getattr(before, key) != getattr(after, key)
        )

    def candidate(self, redo):
        if self.generation != self.session.core.generation:
            raise ValueError("История относится к другому проекту")
        source, target = (self.before, self.after) if redo else (self.after, self.before)
        current = self.session.get_map(source.id)
        changes = {}
        for field in self.fields:
            old, new, actual = (
                getattr(source, field),
                getattr(target, field),
                getattr(current, field),
            )
            if field in {"tokens", "layers", "objects", "shapes", "portals"}:
                old_ids, new_ids = {v.id: v for v in old}, {v.id: v for v in new}
                values = {v.id: v for v in actual}
                touched = {
                    key
                    for key in old_ids.keys() | new_ids.keys()
                    if old_ids.get(key) != new_ids.get(key)
                }
                if any(values.get(key) != old_ids.get(key) for key in touched):
                    raise ValueError("Затронутый объект изменён независимо; отмена недоступна")
                order = [
                    value.id for value in actual if value.id not in touched or value.id in new_ids
                ]
                for key in touched:
                    if key in new_ids:
                        values[key] = new_ids[key]
                    else:
                        values.pop(key, None)
                for index, value in enumerate(new):
                    if value.id in touched and value.id not in order:
                        order.insert(min(index, len(order)), value.id)
                changes[field] = (
                    tuple(sorted(values.values(), key=lambda v: v.position))
                    if (field == "layers")
                    else tuple(values[key] for key in order)
                )
            else:
                if actual != old:
                    raise ValueError("Компонент карты изменён независимо")
                changes[field] = new
        return replace(current, **changes)

    def check(self, redo):
        candidate = self.candidate(redo)
        self.session.validate_change(candidate)

    def undo(self):
        self.session._put_map(self.candidate(False))

    def redo(self):
        self.session._put_map(self.candidate(True))


class MapsService(QObject):
    map_changed = Signal(str)
    map_deleted = Signal(str)
    history_blocked = Signal(str)

    def __init__(self, core=None, parent=None):
        super().__init__(parent)
        self.core = core if core is not None else EntitySession(parent=self)
        self._undo = {}
        self.place_card = None
        self.validate_change = lambda document: None
        self.core.replaced.connect(self.reset)
        self.core.entities_deleted.connect(self.notify_deleted)
        self.core.entity_changed.connect(self._entity_changed)

    @property
    def entities(self):
        return self.core.entities

    @property
    def maps(self):
        return MappingProxyType(
            {e.id: self.get_map(e.id) for e in self.entities.summaries() if e.kind == "map"}
        )

    def reset(self):
        for stack in self._undo.values():
            stack.clear()
            stack.deleteLater()
        self._undo.clear()

    def _put(self, document):
        # Undo belongs to Map payload. Entity rename/reparent is a separate Core command.
        document = replace(document, title=self.entities.get(document.id).title)
        self.entities.put_payload(document.id, map_payload(document))
        self.entities.project(document.id, lambda e, p: document)

    def _get(self, key, kind):
        if self.entities.get(key).kind != kind:
            raise ValueError("Ожидается карта")
        return self.entities.project(
            key,
            lambda e, p: MapDocument(
                e.title,
                p.asset_id,
                e.id,
                p.tokens,
                p.grid,
                p.layers,
                p.objects,
                p.layers_initialized,
                p.fog,
                p.shapes,
                p.portals,
            ),
        )

    def card(self, key):
        if self.entities.get(key).kind != "card":
            raise ValueError("Ожидается карточка")

    def _entity_changed(self, key, fields):
        if self.entities.get(key).kind == "map":
            self.map_changed.emit(key)

    def notify_deleted(self, deleted):
        for key in deleted:
            stack = self._undo.pop(key, None)
            if stack is not None:
                stack.clear()
                stack.deleteLater()
            self.map_deleted.emit(key)

    def _put_map(self, document):
        with self.core.transaction():
            self._put(document)
            self.core.after_commit(lambda: self.map_changed.emit(document.id))
            self.core.mark_changed()

    def create_map(self, title, asset_id, parent_id=None):
        document = MapDocument(
            title, asset_id, layers=(MapLayer("Слой 1"),), layers_initialized=True
        )
        with self.core.transaction():
            self.entities.create(
                "map", document.title, map_payload(document), parent_id, id=document.id
            )
            self.core.after_commit(lambda: self.core.entity_created.emit(document.id))
            self.core.after_commit(lambda: self.map_changed.emit(document.id))
            self.core.mark_changed()
        return document

    def initialize_layers(self, map_id):
        document = self.get_map(map_id)
        if not document.layers_initialized:
            # Canonical one-time initialization, never a side effect of refresh or paint.
            self._put_map(
                replace(
                    document,
                    layers=document.layers or (MapLayer("Слой 1"),),
                    layers_initialized=True,
                )
            )

    def plan_delete(self, deleted):
        return {
            document.id: map_payload(
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

    def undo_stack(self, map_id):
        self.get_map(map_id)
        if map_id not in self._undo:
            self._undo[map_id] = GuardedUndoStack(self)
            self._undo[map_id].blocked.connect(self.history_blocked)
            self._undo[map_id].setUndoLimit(200)
        return self._undo[map_id]

    def record_operation(self, map_id, command):
        self.undo_stack(map_id).push(command)

    def get_map(self, map_id):
        return self._get(map_id, "map")

    def commit_placements(self, map_id, tokens):
        self._put_map(replace(self.get_map(map_id), tokens=tuple(tokens)))

    def edit_map(self, map_id, *, command="Изменить карту", **changes):
        if changes.keys() - {
            "tokens",
            "grid",
            "layers",
            "objects",
            "layers_initialized",
            "fog",
            "shapes",
            "portals",
        }:
            raise ValueError("Изменять ID или источник карты этой командой нельзя")
        before = self.get_map(map_id)
        if "layers" in changes:
            changes["layers_initialized"] = True
        after = replace(before, **changes)
        if before != after:
            operation = MapEdit(self, before, after, command)
            operation.check(True)
            self.undo_stack(map_id).push(operation)

    def put_vector(self, map_id, value):
        from lodandsy.domain.map_document import MapPortal, MapShape

        if not isinstance(value, (MapShape, MapPortal)):
            raise ValueError("Ожидается фигура или портал")
        field = "shapes" if isinstance(value, MapShape) else "portals"
        document = self.get_map(map_id)
        values = getattr(document, field)
        updated = tuple(value if v.id == value.id else v for v in values)
        if not any(v.id == value.id for v in values):
            updated += (value,)
        self.edit_map(
            map_id,
            command="Изменить фигуру" if field == "shapes" else "Изменить портал",
            **{field: updated},
        )

    def delete_vector(self, map_id, key):
        document = self.get_map(map_id)
        changes = {
            field: tuple(v for v in getattr(document, field) if v.id != key)
            for field in ("shapes", "portals")
        }
        self.edit_map(map_id, command="Удалить фигуру или портал", **changes)

    def edit_fog(self, map_id, path, *, erase=False):
        from lodandsy.application.fog_geometry import apply_fog

        state = apply_fog(self.get_map(map_id).fog, path, erase=erase)
        self.edit_map(map_id, fog=state, command="Открыть область" if erase else "Скрыть область")

    def delete_fog_region(self, map_id, region_id):
        from lodandsy.domain.map_fog import FogState

        state = self.get_map(map_id).fog
        self.edit_map(
            map_id,
            fog=FogState(tuple(r for r in state.regions if r.id != region_id)),
            command="Удалить область тумана",
        )

    def add_token(self, map_id, card_id, x, y, **values):
        if self.place_card is not None:
            return self.place_card(map_id, card_id, x, y, **values)
        self.card(card_id)
        document = self.get_map(map_id)
        token = TokenInstance(card_id, x, y, **values)
        self.edit_map(map_id, tokens=(*document.tokens, token), command="Разместить карточку")
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
