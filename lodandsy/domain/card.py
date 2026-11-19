from dataclasses import dataclass, field
from uuid import UUID, uuid4

DOCUMENT_HEADER = ('<head><meta name="qrichtext" content="1">'
                   '<style>p, li { white-space: pre-wrap; } '
                   'hr { height:1px; border-width:0; }</style></head>')
EMPTY_DOCUMENT = ("<html>" + DOCUMENT_HEADER
                  + '<body><p style="-qt-paragraph-type:empty"><br></p></body></html>')


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
    version: int = field(default=2, init=False)


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
        if not isinstance(self.content, str):
            raise ValueError("Card content must be text")
        if self.portrait is not None and not isinstance(self.portrait, Portrait):
            raise ValueError("Invalid portrait block")
        if len(self.content.encode("utf-8")) > 2**21:
            raise ValueError("Document exceeds 2 MiB")
        object.__setattr__(self, "title", self.title.strip())
