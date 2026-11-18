from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EntitySummary:
    id: str
    kind: str
    title: str
    parent_id: str | None
    position: int
