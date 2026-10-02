from dataclasses import dataclass, field
from uuid import uuid4


def _new_id() -> str:
    return str(uuid4())


@dataclass
class Card:
    title: str
    id: str = field(default_factory=_new_id)
    parent_id: str | None = None
    content: str = ""