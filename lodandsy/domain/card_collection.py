from collections.abc import Iterable
from dataclasses import replace

from lodandsy.domain.card import Card
from lodandsy.domain.entity_summary import EntitySummary


class CardCollection:
    def __init__(self, cards: Iterable[Card] = ()) -> None:
        self._cards: dict[str, Card] = {}
        # Ordered sets allow insertion/removal without scanning siblings.
        self._children: dict[str | None, dict[str, None]] = {None: {}}
        for card in cards:
            if card.id in self._cards:
                raise ValueError("Card ids must be unique")
            self._cards[card.id] = card
            self._children.setdefault(card.parent_id, {})[card.id] = None
            self._children.setdefault(card.id, {})
        self._validate_hierarchy()

    def all(self) -> tuple[Card, ...]:
        return tuple(self.get(card_id) for card_id in self.ordered_ids())

    def ordered_ids(self) -> tuple[str, ...]:
        result: list[str] = []
        pending = list(reversed(self._children[None]))
        while pending:
            current_id = pending.pop()
            result.append(current_id)
            pending.extend(reversed(self._children[current_id]))
        return tuple(result)

    def position(self, card_id: str) -> int:
        card = self.get(card_id)
        return tuple(self._children[card.parent_id]).index(card_id)

    def summaries(self) -> tuple[EntitySummary, ...]:
        positions = {
            card_id: position for siblings in self._children.values()
            for position, card_id in enumerate(siblings)
        }
        return tuple(
            EntitySummary(card.id, "card", card.title, card.parent_id, positions[card.id])
            for card in self.all()
        )

    def get(self, card_id: str) -> Card:
        try:
            return self._cards[card_id]
        except KeyError:
            raise ValueError(f"Unknown card id: {card_id}") from None

    def child_ids(self, parent_id: str | None) -> tuple[str, ...]:
        if parent_id is not None:
            self.get(parent_id)
        return tuple(self._children[parent_id])

    def descendant_ids(self, card_id: str) -> tuple[str, ...]:
        self.get(card_id)
        result: list[str] = []
        pending = list(reversed(self._children[card_id]))
        while pending:
            current_id = pending.pop()
            result.append(current_id)
            pending.extend(reversed(self._children[current_id]))
        return tuple(result)

    def create(self, title: str, parent_id: str | None = None, *, content: str = "") -> Card:
        if parent_id is not None:
            self.get(parent_id)
        card = Card(title=title, parent_id=parent_id, content=content)
        if card.id in self._cards:
            raise ValueError("Card ids must be unique")
        self._cards[card.id] = card
        self._children[parent_id][card.id] = None
        self._children[card.id] = {}
        return card

    def update(self, card_id: str, **changes: object) -> Card:
        if changes.keys() - {"title", "content", "parent_id", "position"}:
            raise ValueError("Only title, content, parent_id and position may be changed")
        current = self.get(card_id)
        position = changes.pop("position", None)
        if position is not None and (type(position) is not int or position < 0):
            raise ValueError("Position must be a nonnegative integer")
        updated = replace(current, **changes)
        if updated.parent_id != current.parent_id:
            self._validate_parent(card_id, updated.parent_id)
        moving = updated.parent_id != current.parent_id or position is not None
        if moving:
            destination = [key for key in self._children[updated.parent_id] if key != card_id]
            if position is None:
                position = len(destination)
            if position > len(destination):
                raise ValueError("Position is outside sibling range")
            destination.insert(position, card_id)
        if updated == current and not moving:
            return current
        if moving:
            del self._children[current.parent_id][card_id]
            self._children[updated.parent_id] = dict.fromkeys(destination)
        self._cards[card_id] = updated
        return updated

    def rename(self, card_id: str, title: str) -> None:
        self.update(card_id, title=title)

    def update_content(self, card_id: str, content: str) -> None:
        self.update(card_id, content=content)

    def reparent(self, card_id: str, parent_id: str | None) -> None:
        self.update(card_id, parent_id=parent_id)

    def delete(self, card_id: str) -> tuple[str, ...]:
        card = self.get(card_id)
        deleted_ids = (card_id, *self.descendant_ids(card_id))
        del self._children[card.parent_id][card_id]
        for deleted_id in deleted_ids:
            del self._cards[deleted_id]
            del self._children[deleted_id]
        return deleted_ids

    def _validate_hierarchy(self) -> None:
        # Validate a loaded forest in O(n), including arbitrarily deep trees.
        complete: set[str] = set()
        for card_id in self._cards:
            path: set[str] = set()
            current_id: str | None = card_id
            while current_id is not None and current_id not in complete:
                if current_id in path:
                    raise ValueError("Existing card hierarchy contains a cycle")
                path.add(current_id)
                current_id = self.get(current_id).parent_id
            complete.update(path)

    def _validate_parent(self, card_id: str, parent_id: str | None) -> None:
        current_id = parent_id
        while current_id is not None:
            if current_id == card_id:
                raise ValueError("Reparenting would create a cycle")
            current_id = self.get(current_id).parent_id
