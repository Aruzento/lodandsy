from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from functools import wraps
from uuid import uuid4

from lodandsy.domain.module_values import validate_id, validate_title

DOCUMENT_KINDS = frozenset({"card", "map", "table"})


def atomic_change(operation):
    @wraps(operation)
    def change(self, *args, **kwargs):
        with self.atomic():
            return operation(self, *args, **kwargs)

    return change


@dataclass(frozen=True, slots=True)
class Entity:
    id: str
    kind: str
    title: str
    parent_id: str | None = None
    position: int = 0

    def __post_init__(self):
        validate_id(self.id)
        if self.kind not in DOCUMENT_KINDS:
            raise ValueError(f"Unsupported entity kind: {self.kind}")
        object.__setattr__(self, "title", validate_title(self.title))
        if self.parent_id is not None:
            validate_id(self.parent_id)
            if self.parent_id == self.id:
                raise ValueError("An entity cannot be its own parent")
        if type(self.position) is not int or self.position < 0:
            raise ValueError("Position must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class AggregateChange:
    id: str
    before: Entity | None
    before_payload: object
    after: Entity | None
    after_payload: object


@dataclass(frozen=True, slots=True)
class ChangeSet:
    aggregates: tuple[AggregateChange, ...]
    settings_before: object
    settings_after: object

    @property
    def settings_changed(self):
        return self.settings_before != self.settings_after

    @property
    def previous_payloads(self):
        return {change.id: change.before_payload for change in self.aggregates if change.before}

    def __bool__(self):
        return bool(self.aggregates) or self.settings_changed


@dataclass
class _Savepoint:
    settings: object
    records: dict = field(default_factory=dict)
    children: dict = field(default_factory=dict)


class EntityCollection:
    """One forest and one immutable module payload per ID. No Qt or persistence."""

    def __init__(self, records=(), *, settings=None, validator=None):
        self.settings = settings
        self.validator = validator
        self.change_validator = None
        self._savepoints = []
        self._entities, self._payloads = {}, {}
        self._projections = {}
        for entity, payload in records:
            if entity.id in self._entities:
                raise ValueError("Entity ids must be unique")
            self._entities[entity.id] = entity
            self._payloads[entity.id] = payload
        self._children = {None: {}}
        for entity in self._entities.values():
            self._children.setdefault(entity.id, {})
        grouped = {}
        for entity in self._entities.values():
            if entity.parent_id is not None and entity.parent_id not in self._entities:
                raise ValueError("Unknown entity parent")
            grouped.setdefault(entity.parent_id, []).append(entity)
        for parent, siblings in grouped.items():
            siblings.sort(key=lambda item: item.position)
            if [item.position for item in siblings] != list(range(len(siblings))):
                raise ValueError("Invalid sibling positions")
            self._children[parent] = dict.fromkeys(item.id for item in siblings)
        complete = set()
        for key in self._entities:
            path, current = set(), key
            while current is not None and current not in complete:
                if current in path:
                    raise ValueError("Entity hierarchy contains a cycle")
                path.add(current)
                current = self.get(current).parent_id
            complete.update(path)
        if self.validator is not None:
            self.validator(self, None)

    def get(self, key):
        try:
            return self._entities[key]
        except KeyError:
            raise ValueError(f"Unknown entity id: {key}") from None

    @contextmanager
    def atomic(self):
        savepoint = _Savepoint(self.settings)
        self._savepoints.append(savepoint)
        try:
            yield self
            if len(self._savepoints) == 1 and self.validator is not None:
                changes = self.pending_changes()
                if self.change_validator is None:
                    self.validator(self, changes.previous_payloads)
                else:
                    self.change_validator(self, changes)
        except BaseException:
            self._restore_savepoint(savepoint)
            raise
        else:
            if len(self._savepoints) > 1:
                parent = self._savepoints[-2]
                for key, record in savepoint.records.items():
                    parent.records.setdefault(key, record)
                for key, children in savepoint.children.items():
                    parent.children.setdefault(key, children)
        finally:
            self._savepoints.pop()

    def pending_changes(self):
        savepoint = self._savepoints[-1]
        result = []
        for key, (before, payload, _) in savepoint.records.items():
            after, data = self._entities.get(key), self._payloads.get(key)
            if (before != after) or (payload is not data and payload != data):
                result.append(AggregateChange(key, before, payload, after, data))
        return ChangeSet(tuple(result), savepoint.settings, self.settings)

    def _remember_record(self, key):
        records = self._savepoints[-1].records
        if key not in records:
            records[key] = (
                self._entities.get(key), self._payloads.get(key), self._projections.get(key),
            )

    def _remember_children(self, parent):
        children = self._savepoints[-1].children
        if parent not in children:
            bucket = self._children.get(parent)
            children[parent] = None if bucket is None else bucket.copy()

    def _restore_savepoint(self, savepoint):
        self.settings = savepoint.settings
        for key, (entity, payload, projection) in savepoint.records.items():
            if entity is None:
                self._entities.pop(key, None)
                self._payloads.pop(key, None)
            else:
                self._entities[key], self._payloads[key] = entity, payload
            if projection is None:
                self._projections.pop(key, None)
            else:
                self._projections[key] = projection
        for key, children in savepoint.children.items():
            if children is None:
                self._children.pop(key, None)
            else:
                self._children[key] = children

    @atomic_change
    def put_settings(self, settings):
        if self.settings is not None and type(settings) is not type(self.settings):
            raise ValueError("Project settings kind cannot change")
        self.settings = settings

    def payload(self, key):
        self.get(key)
        return self._payloads[key]

    def project(self, key, factory):
        entity, payload = self.get(key), self.payload(key)
        cached = self._projections.get(key)
        if cached is None or cached[0] is not entity or cached[1] is not payload:
            cached = (entity, payload, factory(entity, payload))
            self._projections[key] = cached
        return cached[2]

    def summaries(self):
        result, pending = [], list(reversed(self._children[None]))
        while pending:
            key = pending.pop()
            result.append(self.get(key))
            pending.extend(reversed(self._children[key]))
        return tuple(result)

    def child_ids(self, parent=None):
        if parent is not None:
            self.get(parent)
        return tuple(self._children[parent])

    def descendant_ids(self, key):
        self.get(key)
        result, pending = [], list(reversed(self._children[key]))
        while pending:
            current = pending.pop()
            result.append(current)
            pending.extend(reversed(self._children[current]))
        return tuple(result)

    @atomic_change
    def create(self, kind, title, payload, parent_id=None, *, id=None):
        if parent_id is not None:
            self.get(parent_id)
        entity = Entity(id or str(uuid4()), kind, title, parent_id, len(self._children[parent_id]))
        if entity.id in self._entities:
            raise ValueError("Duplicate entity ID; ids must be unique")
        self._remember_record(entity.id)
        self._remember_children(parent_id)
        self._remember_children(entity.id)
        self._entities[entity.id], self._payloads[entity.id] = entity, payload
        self._children[parent_id][entity.id] = None
        self._children[entity.id] = {}
        return entity

    @atomic_change
    def update(self, key, **changes):
        if changes.keys() - {"title", "parent_id", "position"}:
            raise ValueError("Only title, parent_id and position may be changed")
        before = self.get(key)
        after = replace(before, **changes)
        moving = before.parent_id != after.parent_id or "position" in changes
        if before == after and not moving:
            return before
        if moving:
            current = after.parent_id
            while current is not None:
                if current == key:
                    raise ValueError("Reparenting would create a cycle")
                current = self.get(current).parent_id
            destination = [item for item in self._children[after.parent_id] if item != key]
            position = changes.get("position", len(destination))
            if position > len(destination):
                raise ValueError("Position is outside sibling range")
            destination.insert(position, key)
            self._remember_children(before.parent_id)
            self._remember_children(after.parent_id)
            del self._children[before.parent_id][key]
            self._children[after.parent_id] = dict.fromkeys(destination)
            self._remember_record(key)
            self._entities[key] = after
            for parent in {before.parent_id, after.parent_id}:
                for index, item in enumerate(self._children[parent]):
                    self._set_position(item, parent, index)
        else:
            self._remember_record(key)
            self._entities[key] = after
        return self.get(key)

    def _set_position(self, key, parent, position):
        entity = self.get(key)
        if (entity.parent_id, entity.position) != (parent, position):
            self._remember_record(key)
            self._entities[key] = replace(entity, parent_id=parent, position=position)

    @atomic_change
    def put_payload(self, key, payload):
        self.get(key)
        previous = self._payloads[key]
        if type(payload) is not type(previous):
            raise ValueError("Entity payload kind cannot change")
        validate = getattr(payload, "validate_replacement", None)
        if validate is not None:
            validate(previous)
        if self._payloads[key] != payload:
            self._remember_record(key)
            self._payloads[key] = payload

    @atomic_change
    def delete(self, key):
        before = self.get(key)
        deleted = (key, *self.descendant_ids(key))
        self._remember_children(before.parent_id)
        del self._children[before.parent_id][key]
        for item in deleted:
            self._remember_record(item)
            self._remember_children(item)
            del self._entities[item], self._payloads[item], self._children[item]
            self._projections.pop(item, None)
        for position, item in enumerate(self._children[before.parent_id]):
            self._set_position(item, before.parent_id, position)
        return deleted
