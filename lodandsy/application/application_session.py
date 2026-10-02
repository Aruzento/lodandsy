from PySide6.QtCore import QObject, Signal

from lodandsy.domain.card import Card
from lodandsy.domain.card_collection import CardCollection


class ApplicationSession(QObject):
    current_card_changed = Signal(object)

    def __init__(
        self,
        cards: CardCollection,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)

        self.cards = cards
        self._current_card_id: str | None = None

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