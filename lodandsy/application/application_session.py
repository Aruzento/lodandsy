from PySide6.QtCore import QObject, Signal

from lodandsy.domain.card import Card
from lodandsy.domain.card_collection import CardCollection
from lodandsy.domain.card_templates import card_template


class ApplicationSession(QObject):
    current_entity_changed = Signal(object)
    entity_changed = Signal(str, object)
    entities_deleted = Signal(object)
    entities_replaced = Signal()
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
        self._current_entity_id: str | None = None

    @property
    def entities(self):
        return self.cards.entities

    @property
    def current_entity_id(self):
        return self._current_entity_id

    @property
    def current_entity(self):
        return self.entities.get(self.current_entity_id) if self.current_entity_id else None

    def select_entity(self, key):
        self.entities.get(key)
        if key != self._current_entity_id:
            self._current_entity_id = key
            self.current_entity_changed.emit(key)
            self.current_card_changed.emit(self.current_card_id)

    def update_entity(self, key, **changes):
        before = self.entities.get(key)
        after = self.entities.update(key, **changes)
        fields = frozenset(k for k in ("title", "parent_id", "position")
                           if getattr(before, k) != getattr(after, k))
        if fields:
            self.entity_changed.emit(key, fields)
            if after.kind == "card":
                self.card_changed.emit(key, fields)
        return after

    def delete_entity(self, key):
        deleted = self.entities.delete(key)
        if self.current_entity_id in deleted:
            self.clear_selection()
        self.entities_deleted.emit(deleted)
        self.cards_deleted.emit(deleted)
        return deleted

    def create_card(self, title: str, parent_id: str | None = None, *, template_id="empty") -> Card:
        template = card_template(template_id)
        card = self.cards.create(title, parent_id, content=template.content,
                                 portrait=template.portrait)
        self.card_created.emit(card.id)
        return card

    def update_card(self, card_id: str, **changes: object) -> Card:
        previous = self.cards.get(card_id)
        if "content" in changes:
            from lodandsy.application.rich_html import validate_html

            validate_html(changes["content"])
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
        self.cards.get(card_id)
        return self.delete_entity(card_id)

    def replace_cards(self, cards: CardCollection):
        self.clear_selection()
        self.cards = cards
        self.cards_replaced.emit()
        self.entities_replaced.emit()

    @property
    def current_card_id(self) -> str | None:
        entity = self.current_entity
        return entity.id if entity and entity.kind == "card" else None

    @property
    def current_card(self) -> Card | None:
        if self.current_card_id is None:
            return None

        return self.cards.get(
            self.current_card_id
        )

    def select_card(
        self,
        card_id: str,
    ) -> None:
        self.cards.get(card_id)

        self.select_entity(card_id)

    def clear_selection(self) -> None:
        if self._current_entity_id is None:
            return

        self._current_entity_id = None
        self.current_entity_changed.emit(None)

        self.current_card_changed.emit(None)
