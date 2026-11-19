from PySide6.QtCore import QObject, Signal

from lodandsy.domain.card import EMPTY_DOCUMENT, Card
from lodandsy.domain.card_collection import CardCollection
from lodandsy.domain.card_schema import FIELD_DEFINITIONS


class ApplicationSession(QObject):
    field_draft_changed = Signal(str, object)
    current_entity_changed = Signal(object)
    entity_changed = Signal(str, object)
    entities_deleted = Signal(object)
    entities_replaced = Signal()
    current_card_changed = Signal(object)
    entity_created = Signal(str)
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
        self.field_drafts = {}
        self.deletion_planners = []

    def set_field_draft(self, key, field, raw):
        self.cards.get(key)
        identity = key, field
        before = self.field_drafts.get(identity)
        if raw is None:
            self.field_drafts.pop(identity, None)
        else:
            self.field_drafts[identity] = raw
        if before != raw:
            self.field_draft_changed.emit(key, frozenset({field}))

    def discard_field_drafts(self, key):
        for identity in tuple(self.field_drafts):
            if identity[0] == key:
                self.set_field_draft(key, identity[1], None)

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
        if before.kind == "card":
            if changes.keys() - {"title", "parent_id", "position"}:
                raise ValueError("Only title, parent_id and position may be changed")
            self.update_card(key, **changes)
            return self.entities.get(key)
        after = self.entities.update(key, **changes)
        fields = frozenset(
            k for k in ("title", "parent_id", "position") if getattr(before, k) != getattr(after, k)
        )
        if fields:
            self.entity_changed.emit(key, fields)
            if after.kind == "card":
                self.card_changed.emit(key, fields)
        return after

    def delete_entity(self, key):
        planned = (key, *self.entities.descendant_ids(key))
        changes = {}
        for planner in self.deletion_planners:
            changes.update(planner(frozenset(planned)))
        with self.entities.atomic():
            for identity, payload in changes.items():
                self.entities.put_payload(identity, payload)
            deleted = self.entities.delete(key)
        for identity in tuple(self.field_drafts):
            if identity[0] in deleted:
                self.field_drafts.pop(identity, None)
        if self.current_entity_id in deleted:
            self.clear_selection()
        self.entities_deleted.emit(deleted)
        for identity in changes:
            self.entity_changed.emit(identity, frozenset({"payload"}))
        self.cards_deleted.emit(deleted)
        return deleted

    def create_card(self, title, parent_id=None, *, card_type="note"):
        card = self.cards.create(title, parent_id, card_type=card_type)
        self.card_created.emit(card.id)
        return card

    def add_card_field(self, card_id, key):
        after = self.cards.get(card_id).add_field(key)
        return self.update_card(card_id, values=after.values)

    def update_section(self, card_id, section_id, **changes):
        from dataclasses import replace

        if changes.keys() - {"title", "content", "table_id"}:
            raise ValueError("Неподдерживаемые изменения раздела")
        card = self.cards.get(card_id)
        card.section(section_id)
        sections = tuple(
            replace(section, **changes) if section.id == section_id else section
            for section in card.sections
        )
        return self.update_card(card_id, sections=sections)

    def add_section(self, card_id, title, *, kind="rich_text", table_id=None):
        from lodandsy.domain.card import CardSection

        card = self.cards.get(card_id)
        if table_id is not None:
            entity = self.entities.get(table_id)
            if entity.kind != "table" or entity.parent_id != card_id:
                raise ValueError("Выберите дочернюю таблицу карточки")
        section = CardSection(
            title,
            len(card.sections),
            kind,
            content=EMPTY_DOCUMENT if kind == "rich_text" else None,
            table_id=table_id,
        )
        self.update_card(card_id, sections=(*card.sections, section))
        return section

    def delete_section(self, card_id, key):
        from dataclasses import replace

        card = self.cards.get(card_id)
        card.section(key)
        sections = tuple(
            replace(s, position=i) for i, s in enumerate(s for s in card.sections if s.id != key)
        )
        self.update_card(card_id, sections=sections)
        self.set_field_draft(card_id, key, None)

    def move_section(self, card_id, key, position):
        from dataclasses import replace

        card = self.cards.get(card_id)
        sections = list(card.sections)
        if type(position) is not int or not 0 <= position < len(sections):
            raise ValueError("Invalid section position")
        section = card.section(key)
        sections.remove(section)
        sections.insert(position, section)
        self.update_card(
            card_id, sections=tuple(replace(s, position=i) for i, s in enumerate(sections))
        )

    def section_table(self, card_id, key, *, existing_id=None, replace_link=False, title=None):
        from dataclasses import replace

        from lodandsy.domain.document_payloads import module_document, module_payload
        from lodandsy.domain.table_document import ColumnDefinition, TableDocument

        card = self.cards.get(card_id)
        section = card.section(key)
        if section.kind != "table_ref":
            raise ValueError("Это не табличный раздел")
        if section.table_id and not replace_link:
            entity = self.entities.get(section.table_id)
            if entity.kind != "table" or entity.parent_id != card_id:
                raise ValueError("Связанная дочерняя таблица недоступна")
            return module_document(self.entities, entity.id)
        if existing_id:
            entity = self.entities.get(existing_id)
            if entity.kind != "table" or entity.parent_id != card_id:
                raise ValueError("Выберите дочернюю таблицу")
            table = module_document(self.entities, existing_id)
            create = False
        else:
            columns = tuple(
                ColumnDefinition(name, kind, i)
                for i, (name, kind) in enumerate(
                    [("Предмет", "text"), ("Количество", "number"), ("Описание", "text")]
                    if section.purpose == "inventory"
                    else [("Столбец 1", "text")]
                )
            )
            table = TableDocument(title or section.title, columns=columns)
            create = True
        candidate = replace(
            card,
            sections=tuple(
                replace(s, table_id=table.id) if s.id == key else s for s in card.sections
            ),
        )
        with self.entities.atomic():
            if create:
                self.entities.create(
                    "table", table.title, module_payload(table), card_id, id=table.id
                )
            self.entities.put_payload(card_id, candidate.payload())
        if create:
            self.entity_created.emit(table.id)
        self.card_changed.emit(card_id, frozenset({"sections", key}))
        return table

    def update_card_fields(self, card_id, changes):
        if not isinstance(changes, dict):
            raise ValueError("Ожидается набор полей")
        before = self.cards.get(card_id)
        after = before.with_fields(changes)
        return self.update_card(
            card_id,
            title=after.title,
            sections=after.sections,
            portrait=after.portrait,
            values=after.values,
        )

    def update_card(self, card_id: str, **changes: object) -> Card:
        previous = self.cards.get(card_id)
        if "content" in changes:
            from lodandsy.application.rich_html import validate_html

            validate_html(changes["content"])
        if "sections" in changes:
            from lodandsy.application.rich_html import validate_html

            for section in changes["sections"]:
                if section.kind == "rich_text":
                    validate_html(section.content)
        previous_position = (
            self.cards.position(card_id) if changes.keys() & {"position", "parent_id"} else None
        )
        card = self.cards.update(card_id, **changes)
        fields = frozenset(
            field
            for field in changes
            if field not in {"position", "values", "content"}
            if getattr(previous, field) != getattr(card, field)
        )
        old_sections = {s.id: s for s in previous.sections}
        new_sections = {s.id: s for s in card.sections}
        fields |= {
            key
            for key in old_sections.keys() | new_sections.keys()
            if old_sections.get(key) != new_sections.get(key)
        }
        fields |= set(dict(previous.values)) ^ set(dict(card.values))
        fields |= {key for key in FIELD_DEFINITIONS if previous.value(key) != card.value(key)}
        if previous_position is not None and previous_position != self.cards.position(card_id):
            fields |= {"position"}
        if fields:
            structural = fields & {"title", "parent_id", "position"}
            if structural:
                self.entity_changed.emit(card_id, structural)
            self.card_changed.emit(card_id, fields)
        return card

    def delete_card(self, card_id: str) -> tuple[str, ...]:
        self.cards.get(card_id)
        return self.delete_entity(card_id)

    def replace_cards(self, cards: CardCollection):
        self.clear_selection()
        self.field_drafts.clear()
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

        return self.cards.get(self.current_card_id)

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
