from dataclasses import replace

from lodandsy.domain.card import EMPTY_DOCUMENT, Card
from lodandsy.domain.document_payloads import project_entities


class CardCollection:
    """Card operations over the shared forest; returned Cards are immutable projections."""

    def __init__(self, cards=(), *, entities=None):
        self.entities = entities if entities is not None else project_entities(cards)

    def all(self):
        return tuple(self.get(e.id) for e in self.entities.summaries() if e.kind == "card")

    def ordered_ids(self):
        return tuple(card.id for card in self.all())

    def position(self, key):
        self.get(key)
        return self.entities.get(key).position

    def summaries(self):
        return tuple(e for e in self.entities.summaries() if e.kind == "card")

    def get(self, key):
        entity = self.entities.get(key)
        if entity.kind != "card":
            raise ValueError(f"Not a Card: {key}")
        return self.entities.project(
            key,
            lambda e, p: Card(
                e.title,
                key,
                e.parent_id,
                portrait=p.portrait,
                card_type=p.card_type,
                values=p.values,
                sections=p.sections,
            ),
        )

    def child_ids(self, parent_id):
        return self.entities.child_ids(parent_id)

    def descendant_ids(self, key):
        return self.entities.descendant_ids(key)

    def create(
        self,
        title,
        parent_id=None,
        *,
        content=EMPTY_DOCUMENT,
        portrait=None,
        card_type="note",
        sections=None,
        values=(),
    ):
        card = Card(
            title,
            parent_id=parent_id,
            content=content,
            portrait=portrait,
            card_type=card_type,
            sections=sections,
            values=values,
        )
        self.entities.create("card", card.title, card.payload(), parent_id, id=card.id)
        return self.get(card.id)

    def update(self, key, **changes):
        if changes.keys() - {
            "title",
            "parent_id",
            "position",
            "content",
            "portrait",
            "card_type",
            "sections",
            "values",
        }:
            raise ValueError("Unsupported Card fields")
        current = self.get(key)
        if "content" in changes:
            body = current.with_fields({"description": changes.pop("content")})
            changes["sections"] = body.sections
        updated = replace(current, **{k: v for k, v in changes.items() if k != "position"})
        self.entities.update(
            key, **{k: v for k, v in changes.items() if k in {"title", "parent_id", "position"}}
        )
        self.entities.put_payload(key, updated.payload())
        return self.get(key)

    def rename(self, key, title):
        self.update(key, title=title)

    def update_content(self, key, content):
        self.update(key, content=content)

    def reparent(self, key, parent_id):
        self.update(key, parent_id=parent_id)

    def delete(self, key):
        self.get(key)
        return self.entities.delete(key)
