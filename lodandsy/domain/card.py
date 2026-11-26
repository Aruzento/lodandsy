import math
from dataclasses import dataclass, field, replace
from uuid import UUID, uuid4

from lodandsy.domain.actor_state import ActorState
from lodandsy.domain.card_schema import (
    ACTOR_TYPES,
    CARD_TYPES,
    available_fields,
    field_definition,
    validate_fields,
)

DOCUMENT_HEADER = (
    '<head><meta name="qrichtext" content="1">'
    "<style>p, li { white-space: pre-wrap; } "
    "hr { height:1px; border-width:0; }</style></head>"
)
EMPTY_DOCUMENT = (
    "<html>" + DOCUMENT_HEADER + '<body><p style="-qt-paragraph-type:empty"><br></p></body></html>'
)


def validate_card_id(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("Card id must be a canonical UUID string")
    try:
        parsed = UUID(value)
    except ValueError:
        raise ValueError("Card id must be a canonical UUID string") from None
    if str(parsed) != value:
        raise ValueError("Card id must be a canonical UUID string")


@dataclass(frozen=True, slots=True)
class Portrait:
    asset_id: str | None = None
    crop: tuple = (0.0, 0.0, 1.0, 1.0)

    def __post_init__(self):
        if self.asset_id is not None:
            validate_card_id(self.asset_id)
        if not isinstance(self.crop, tuple) or len(self.crop) != 4:
            raise ValueError("Invalid portrait crop")
        x, y, w, h = self.crop
        if not all(type(v) in (int, float) and math.isfinite(v) for v in self.crop) or not (
            0 <= x < 1
            and 0 <= y < 1
            and 0 < w <= 1
            and 0 < h <= 1
            and x + w <= 1.000000001
            and y + h <= 1.000000001
        ):
            raise ValueError("Invalid portrait crop")


@dataclass(frozen=True, slots=True)
class CardSection:
    title: str
    position: int = 0
    kind: str = "rich_text"
    id: str = field(default_factory=lambda: str(uuid4()))
    content: str | None = EMPTY_DOCUMENT
    table_id: str | None = None
    purpose: str | None = None

    def __post_init__(self):
        validate_card_id(self.id)
        field_definition("title").validate(self.title)
        if (
            not self.title.strip()
            or any(c in self.title for c in "\r\n\0")
            or type(self.position) is not int
            or self.position < 0
        ):
            raise ValueError("Invalid section title/order")
        if self.purpose not in {None, "description", "inventory", "relations"}:
            raise ValueError("Invalid section purpose")
        if self.kind == "rich_text":
            if (
                self.table_id is not None
                or not isinstance(self.content, str)
                or len(self.content.encode("utf-8")) > 2**21
            ):
                raise ValueError("Invalid rich text section / 2 MiB budget")
        elif self.kind == "table_ref":
            if self.content is not None:
                raise ValueError("Table section has no copied content")
            if self.table_id is not None:
                validate_card_id(self.table_id)
        else:
            raise ValueError("Unsupported section kind")


def initial_sections(card_type):
    definition = CARD_TYPES[card_type]
    entries = definition.initial_sections or (("Описание", "rich_text", "description"),)
    return tuple(
        CardSection(
            title, i, kind, content=EMPTY_DOCUMENT if kind == "rich_text" else None, purpose=purpose
        )
        for i, (title, kind, purpose) in enumerate(entries)
    )


@dataclass(frozen=True, slots=True)
class CardPayload:
    sections: tuple
    portrait: Portrait | None = None
    card_type: str = "note"
    values: tuple = ()
    actors: tuple = ()
    default_actor_id: str | None = None
    version: int = field(default=7, init=False)

    def validate_replacement(self, previous):
        if self.card_type != previous.card_type:
            raise ValueError("Тип карточки после создания неизменяемый")

    def __post_init__(self):
        if not isinstance(self.card_type, str) or self.card_type not in CARD_TYPES:
            raise ValueError("Неизвестный тип карточки")
        if self.portrait is not None and not isinstance(self.portrait, Portrait):
            raise ValueError("Invalid portrait")
        if (
            not isinstance(self.sections, tuple)
            or len(self.sections) > 64
            or not all(isinstance(s, CardSection) for s in self.sections)
        ):
            raise ValueError("Invalid sections")
        if len({s.id for s in self.sections}) != len(self.sections) or [
            s.position for s in self.sections
        ] != list(range(len(self.sections))):
            raise ValueError("Duplicate section or invalid order")
        purposes = [s.purpose for s in self.sections if s.purpose]
        if len(purposes) != len(set(purposes)):
            raise ValueError("Duplicate canonical section purpose")
        if sum(len((s.content or "").encode("utf-8")) for s in self.sections) > 4 * 2**20:
            raise ValueError("Card rich text exceeds 4 MiB")
        if not isinstance(self.values, tuple):
            raise ValueError("Card fields must be immutable")
        validate_fields(self.card_type, self.values)
        from lodandsy.domain.rules_5e14 import DEFAULT_FORMULAS

        for modifier in dict(self.values).get("modifiers", ()):
            if modifier.target not in DEFAULT_FORMULAS:
                raise ValueError("Unknown modifier target: " + modifier.target)
        if (
            not isinstance(self.actors, tuple)
            or not all(isinstance(actor, ActorState) for actor in self.actors)
            or len(self.actors) > 10000
        ):
            raise ValueError("Invalid Actor collection")
        if self.actors and self.card_type not in ACTOR_TYPES:
            raise ValueError("Card type does not support Actors")
        if len({a.id for a in self.actors}) != len(self.actors):
            raise ValueError("Duplicate Actor UUID")
        object.__setattr__(self, "actors", tuple(sorted(self.actors, key=lambda a: a.id)))
        for actor in self.actors:
            validate_fields(self.card_type, actor.values, "actor")
        if self.default_actor_id is not None and self.default_actor_id not in {
            a.id for a in self.actors
        }:
            raise ValueError("Default Actor is missing")
        keys = set()
        for key, value in self.values:
            definition = field_definition(key)
            if definition.key in {"title", "description"} or key in keys:
                raise ValueError("Duplicate canonical Card field")
            definition.validate(value)
            if key == "token_kind" and value not in {None, "character", "item"}:
                raise ValueError("Invalid token kind")
            keys.add(key)
        object.__setattr__(self, "values", tuple(sorted(self.values)))


@dataclass(frozen=True, slots=True, init=False)
class Card:
    title: str
    id: str
    parent_id: str | None
    sections: tuple
    portrait: Portrait | None
    card_type: str
    values: tuple
    actors: tuple
    default_actor_id: str | None

    def __init__(
        self,
        title,
        id=None,
        parent_id=None,
        content=None,
        portrait=None,
        card_type="note",
        values=(),
        sections=None,
        actors=(),
        default_actor_id=None,
    ):
        identity = str(uuid4()) if id is None else id
        validate_card_id(identity)
        if parent_id is not None:
            validate_card_id(parent_id)
        if parent_id == identity:
            raise ValueError("A card cannot be its own parent")
        if not isinstance(title, str) or not title.strip() or any(c in title for c in "\r\n\0"):
            raise ValueError("Card title must be a nonempty single line")
        field_definition("title").validate(title)
        if not isinstance(card_type, str) or card_type not in CARD_TYPES:
            raise ValueError("Неизвестный тип карточки")
        if sections is None:
            sections = initial_sections(card_type)
            if content is not None:
                sections = tuple(
                    replace(s, content=content) if s.purpose == "description" else s
                    for s in sections
                )
        elif content is not None:
            raise ValueError("Content is stored only in sections")
        payload = CardPayload(sections, portrait, card_type, values, actors, default_actor_id)
        for key, value in dict(
            title=title.strip(),
            id=identity,
            parent_id=parent_id,
            sections=payload.sections,
            portrait=portrait,
            card_type=card_type,
            values=payload.values,
            actors=payload.actors,
            default_actor_id=default_actor_id,
        ).items():
            object.__setattr__(self, key, value)

    @property
    def content(self):
        return next(
            (s.content for s in self.sections if s.purpose == "description"), EMPTY_DOCUMENT
        )

    @property
    def description_id(self):
        return next((s.id for s in self.sections if s.purpose == "description"), None)

    def payload(self):
        return CardPayload(
            self.sections,
            self.portrait,
            self.card_type,
            self.values,
            self.actors,
            self.default_actor_id,
        )

    def actor(self, key):
        try:
            return next(actor for actor in self.actors if actor.id == key)
        except StopIteration:
            raise ValueError("Actor отсутствует") from None

    def section(self, key):
        try:
            return next(s for s in self.sections if s.id == key)
        except StopIteration:
            raise ValueError("Раздел удалён или отсутствует") from None

    def value(self, key):
        definition = field_definition(key)
        if definition.key == "title":
            return self.title
        if definition.key == "description":
            return self.content
        return dict(self.values).get(definition.key, definition.default)

    def with_fields(self, changes):
        values, direct, seen = dict(self.values), {}, set()
        for key, value in changes.items():
            definition = field_definition(key)
            definition.validate(value)
            key = definition.key
            if key in seen:
                raise ValueError("Duplicate field alias")
            seen.add(key)
            if key == "title":
                direct["title"] = value
            elif key == "description":
                if not isinstance(value, str):
                    raise ValueError("Rich text content must be a string")
                if self.description_id is None:
                    raise ValueError("Раздел описания удалён")
                direct["sections"] = tuple(
                    replace(s, content=value or EMPTY_DOCUMENT)
                    if s.id == self.description_id
                    else s
                    for s in self.sections
                )
            else:
                values[key] = value
        return replace(self, **direct, values=tuple(values.items()))

    def add_field(self, key):
        if key not in {f.key for f in available_fields(self)}:
            raise ValueError("Поле уже существует или недоступно для этого типа")
        return self.with_fields({key: field_definition(key).default})

    def with_portrait(self, portrait):
        return replace(self, portrait=portrait)
