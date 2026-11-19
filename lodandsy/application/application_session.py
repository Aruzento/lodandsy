from PySide6.QtCore import QObject, Signal

from lodandsy.domain.card import Card
from lodandsy.domain.card_collection import CardCollection
from lodandsy.domain.card_templates import card_template


class ApplicationSession(QObject):
    current_card_changed = Signal(object)
    card_created = Signal(str)
    card_changed = Signal(str, object)
    cards_deleted = Signal(object)
    cards_replaced = Signal()

    def __init__(
        self,
        cards: CardCollection,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)

        self.cards = cards
        self._current_card_id: str | None = None

    def create_card(self, title: str, parent_id: str | None = None, *, template_id="empty") -> Card:
        template = card_template(template_id)
        card = self.cards.create(title, parent_id, content=template.content)
        self.card_created.emit(card.id)
        return card

    def update_card(self, card_id: str, **changes: object) -> Card:
        previous = self.cards.get(card_id)
        previous_position = (
            self.cards.position(card_id) if changes.keys() & {"position", "parent_id"} else None
        )
        card = self.cards.update(card_id, **changes)
        fields = frozenset(
            field for field in changes if field != "position"
            if getattr(previous, field) != getattr(card, field)
        )
        if previous_position is not None and previous_position != self.cards.position(card_id):
            fields |= {"position"}
        if fields:
            self.card_changed.emit(card_id, fields)
        return card

    def delete_card(self, card_id: str) -> tuple[str, ...]:
        deleted_ids = self.cards.delete(card_id)
        if self.current_card_id in deleted_ids:
            self.clear_selection()
        self.cards_deleted.emit(deleted_ids)
        return deleted_ids

    def replace_cards(self, cards: CardCollection):
        self.clear_selection()
        self.cards = cards
        self.cards_replaced.emit()

    @property
    def current_card_id(self) -> str | None:
        return self._current_card_id

    @property
    def current_card(self) -> Card | None:
        if self._current_card_id is None:
            return None

        return self.cards.get(
            self._current_card_id
        )

    def select_card(
        self,
        card_id: str,
    ) -> None:
        self.cards.get(card_id)

        if card_id == self._current_card_id:
            return

        self._current_card_id = card_id

        self.current_card_changed.emit(
            card_id
        )

    def clear_selection(self) -> None:
        if self._current_card_id is None:
            return

        self._current_card_id = None

        self.current_card_changed.emit(None)
