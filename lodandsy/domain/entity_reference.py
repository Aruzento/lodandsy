"""Immutable public query result; no widget, SQL or persisted derived value."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReferenceInfo:
    id: str
    kind: str
    title: str
    path: str = ""
    card_type: str | None = None
    aliases: tuple = ()
    image_id: str | None = None
    fields: tuple = ()

    def value(self, key):
        return next((value for name, value in self.fields if name == key), None)
