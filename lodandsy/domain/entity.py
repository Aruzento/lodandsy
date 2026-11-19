from contextlib import contextmanager
from dataclasses import dataclass, replace
from uuid import uuid4

from lodandsy.domain.module_values import validate_id, validate_title

DOCUMENT_KINDS = frozenset({"card", "map", "table"})


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


class EntityCollection:
    """One forest and one immutable module payload per ID. No Qt or persistence."""

    def __init__(self, records=()):
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

    def get(self, key):
        try:
            return self._entities[key]
        except KeyError:
            raise ValueError(f"Unknown entity id: {key}") from None

    @contextmanager
    def atomic(self):
        before = (
            self._entities.copy(),
            self._payloads.copy(),
            {k: dict(v) for k, v in self._children.items()},
            self._projections.copy(),
        )
        try:
            yield self
        except Exception:
            self._entities, self._payloads, self._children, self._projections = before
            raise

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

    def create(self, kind, title, payload, parent_id=None, *, id=None):
        if parent_id is not None:
            self.get(parent_id)
        entity = Entity(id or str(uuid4()), kind, title, parent_id, len(self._children[parent_id]))
        if entity.id in self._entities:
            raise ValueError("Duplicate entity ID; ids must be unique")
        self._entities[entity.id], self._payloads[entity.id] = entity, payload
        self._children[parent_id][entity.id] = None
        self._children[entity.id] = {}
        return entity

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
            del self._children[before.parent_id][key]
            self._children[after.parent_id] = dict.fromkeys(destination)
            self._entities[key] = after
            for parent in {before.parent_id, after.parent_id}:
                for index, item in enumerate(self._children[parent]):
                    self._entities[item] = replace(self.get(item), parent_id=parent, position=index)
        else:
            self._entities[key] = after
        return self.get(key)

    def put_payload(self, key, payload):
        self.get(key)
        if self._payloads[key] != payload:
            self._payloads[key] = payload

    def delete(self, key):
        before = self.get(key)
        deleted = (key, *self.descendant_ids(key))
        del self._children[before.parent_id][key]
        for item in deleted:
            del self._entities[item], self._payloads[item], self._children[item]
            self._projections.pop(item, None)
        for position, item in enumerate(self._children[before.parent_id]):
            self._entities[item] = replace(self.get(item), position=position)
        return deleted
