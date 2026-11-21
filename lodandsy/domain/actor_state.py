"""Cards-owned identities and addressed typed values; no placement or GUI dependency."""

from dataclasses import dataclass, field, replace
from uuid import uuid4

from lodandsy.domain.card_schema import field_definition
from lodandsy.domain.module_values import validate_id, validate_title


@dataclass(frozen=True, slots=True)
class ActorRef:
    card_id: str
    actor_id: str

    def __post_init__(self):
        validate_id(self.card_id)
        validate_id(self.actor_id)


@dataclass(frozen=True, slots=True)
class ValueAddress:
    card_id: str
    field_id: str
    actor_id: str | None = None

    def __post_init__(self):
        validate_id(self.card_id)
        field_definition(self.field_id) if self.field_id != "actor_name" else None
        if self.field_id != "actor_name":
            object.__setattr__(self, "field_id", field_definition(self.field_id).key)
        if self.actor_id is not None:
            validate_id(self.actor_id)

    def __getitem__(self, index):
        return (self.card_id, self.field_id)[index]

    def __iter__(self):
        return iter((self.card_id, self.field_id))


@dataclass(frozen=True, slots=True)
class VariableValue:
    value: object = None
    presence: str = "absent"
    source: str = "default"
    status: str = "ok"
    diagnostic: str = ""
    dependencies: frozenset = frozenset()


@dataclass(frozen=True, slots=True)
class ActorState:
    name: str
    values: tuple
    id: str = field(default_factory=lambda: str(uuid4()))
    inventory_id: str | None = None
    _validation_proof: tuple | None = field(default=None, init=False, compare=False, repr=False)

    def __post_init__(self):
        validate_id(self.id)
        field_definition("title").validate(self.name)
        object.__setattr__(self, "name", validate_title(self.name))
        if self.inventory_id is not None:
            validate_id(self.inventory_id)
        if not isinstance(self.values, tuple):
            raise ValueError("Actor values must be immutable")
        keys = set()
        for key, value in self.values:
            definition = field_definition(key)
            if definition.scope != "actor" or key in keys:
                raise ValueError("Invalid Actor field scope/duplicate")
            definition.validate(value)
            keys.add(key)
        if not {"hp_current", "hp_temp"} <= keys:
            raise ValueError("Actor state requires current and temporary HP")
        object.__setattr__(self, "values", tuple(sorted(self.values)))

    def value(self, key):
        return dict(self.values).get(key, field_definition(key).default)

    def with_fields(self, changes):
        return replace(self, values=tuple((dict(self.values) | changes).items()))
