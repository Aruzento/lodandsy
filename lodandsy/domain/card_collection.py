from collections.abc import Iterable

from lodandsy.domain.card import Card


class CardCollection:
    def __init__(self, cards: Iterable[Card] = ()) -> None:
        card_list = list(cards)

        self._cards = {
            card.id: card
            for card in card_list
        }

        if len(self._cards) != len(card_list):
            raise ValueError("Card ids must be unique")

        for card in card_list:
            self._validate_parent(
                card.id,
                card.parent_id,
            )

    def all(self) -> tuple[Card, ...]:
        return tuple(self._cards.values())

    def get(self, card_id: str) -> Card:
        try:
            return self._cards[card_id]
        except KeyError:
            raise ValueError(
                f"Unknown card id: {card_id}"
            ) from None

    def create(
        self,
        title: str,
        parent_id: str | None = None,
    ) -> Card:
        if parent_id is not None:
            self.get(parent_id)

        card = Card(
            title=title,
            parent_id=parent_id,
        )

        self._cards[card.id] = card

        return card

    def rename(
        self,
        card_id: str,
        title: str,
    ) -> None:
        card = self.get(card_id)
        card.title = title

    def update_content(
        self,
        card_id: str,
        content: str,
    ) -> None:
        card = self.get(card_id)
        card.content = content

    def reparent(
        self,
        card_id: str,
        parent_id: str | None,
    ) -> None:
        card = self.get(card_id)

        self._validate_parent(
            card_id,
            parent_id,
        )

        card.parent_id = parent_id

    def delete(
        self,
        card_id: str,
    ) -> tuple[str, ...]:
        self.get(card_id)

        deleted_ids = self._collect_subtree_ids(
            card_id
        )

        for deleted_id in deleted_ids:
            del self._cards[deleted_id]

        return tuple(deleted_ids)

    def _collect_subtree_ids(
        self,
        card_id: str,
    ) -> list[str]:
        result: list[str] = []
        pending = [card_id]
        visited: set[str] = set()

        while pending:
            current_id = pending.pop()

            if current_id in visited:
                raise ValueError(
                    "Existing card hierarchy contains a cycle"
                )

            visited.add(current_id)
            result.append(current_id)

            child_ids = [
                card.id
                for card in self._cards.values()
                if card.parent_id == current_id
            ]

            pending.extend(child_ids)

        return result

    def _validate_parent(
        self,
        card_id: str,
        parent_id: str | None,
    ) -> None:
        if parent_id is None:
            return

        if parent_id == card_id:
            raise ValueError(
                "A card cannot be its own parent"
            )

        self.get(parent_id)

        current_id: str | None = parent_id
        visited: set[str] = set()

        while current_id is not None:
            if current_id == card_id:
                raise ValueError(
                    "Reparenting would create a cycle"
                )

            if current_id in visited:
                raise ValueError(
                    "Existing card hierarchy contains a cycle"
                )

            visited.add(current_id)

            current = self.get(current_id)
            current_id = current.parent_id