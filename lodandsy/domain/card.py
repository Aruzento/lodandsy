from dataclasses import dataclass, field
from uuid import UUID, uuid4


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
    content: str = ""

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
        object.__setattr__(self, "title", self.title.strip())
