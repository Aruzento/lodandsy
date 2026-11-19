from dataclasses import dataclass, field
from uuid import UUID, uuid4

from lodandsy.domain.card_schema import CARD_TYPES, field_definition

DOCUMENT_HEADER = (
    '<head><meta name="qrichtext" content="1">'
    "<style>p, li { white-space: pre-wrap; } "
    "hr { height:1px; border-width:0; }</style></head>"
)
EMPTY_DOCUMENT = (
    "<html>" + DOCUMENT_HEADER + '<body><p style="-qt-paragraph-type:empty"><br></p></body></html>'
)


@dataclass(frozen=True, slots=True)
class Portrait:
    asset_id: str | None = None
    alt: str = "Портрет"
    caption: str = ""

    def __post_init__(self):
        if self.asset_id is not None:
            validate_card_id(self.asset_id)
        for value in (self.alt, self.caption):
            if not isinstance(value, str) or len(value) > 2000 or "\x00" in value:
                raise ValueError("Invalid portrait description")


@dataclass(frozen=True, slots=True)
class CardPayload:
    content: str = EMPTY_DOCUMENT
    portrait: Portrait | None = None
    card_type: str = "note"
    template_id: str = "empty"
    values: tuple = ()
    version: int = field(default=3, init=False)

    def __post_init__(self):
        from lodandsy.domain.card_templates import card_template

        if not isinstance(self.card_type, str) or self.card_type not in CARD_TYPES:
            raise ValueError("Неизвестный тип карточки")
        field_definition("description").validate(self.content)
        if self.content is None:
            raise ValueError("Description must be a rich document")
        card_template(self.template_id)
        if not isinstance(self.values, tuple):
            raise ValueError("Card fields must be immutable")
        keys, rich_bytes = set(), len(self.content.encode("utf-8"))
        for pair in self.values:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("Invalid Card field value")
            key, value = pair
            definition = field_definition(key)
            if key in {"name", "title", "description", "portrait"} or key in keys:
                raise ValueError("Duplicate canonical Card field")
            definition.validate(value)
            if key == "token_kind" and value not in {None, "character", "item"}:
                raise ValueError("Вид токена: character или item")
            if definition.data_type == "richtext" and value:
                rich_bytes += len(value.encode("utf-8"))
            keys.add(key)
        if rich_bytes > 4 * 2**20:
            raise ValueError("Card rich text exceeds 4 MiB")
        object.__setattr__(self, "values", tuple(sorted(self.values)))


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
class Card:
    """Immutable snapshot. Resolve the latest state through CardCollection.get(id)."""

    title: str
    id: str = field(default_factory=lambda: str(uuid4()))
    parent_id: str | None = None
    content: str = EMPTY_DOCUMENT
    portrait: Portrait | None = None

    card_type: str = "note"
    template_id: str = "empty"
    values: tuple = ()

    def __post_init__(self) -> None:
        validate_card_id(self.id)
        if self.parent_id is not None:
            validate_card_id(self.parent_id)
            if self.parent_id == self.id:
                raise ValueError("A card cannot be its own parent")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("Card title must not be empty")
        if any(character in self.title for character in "\r\n\x00"):
            raise ValueError("Card title must be a single line")
        field_definition("title").validate(self.title)
        if not isinstance(self.content, str):
            raise ValueError("Card content must be text")
        if self.portrait is not None and not isinstance(self.portrait, Portrait):
            raise ValueError("Invalid portrait block")
        if len(self.content.encode("utf-8")) > 2**21:
            raise ValueError("Document exceeds 2 MiB")
        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "values", self.payload().values)

    def payload(self):
        return CardPayload(
            self.content, self.portrait, self.card_type, self.template_id, self.values
        )

    def value(self, key):
        definition = field_definition(key)
        if definition.key == "title":
            return self.title
        if definition.key == "description":
            return self.content
        if definition.key == "portrait":
            return self.portrait.asset_id if self.portrait else None
        return dict(self.values).get(definition.key, definition.default)

    def with_fields(self, changes):
        from dataclasses import replace

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
                direct["content"] = value or EMPTY_DOCUMENT
            elif key == "portrait":
                direct["portrait"] = replace(self.portrait or Portrait(), asset_id=value)
            else:
                values[key] = value
        return replace(self, **direct, values=tuple(values.items()))
