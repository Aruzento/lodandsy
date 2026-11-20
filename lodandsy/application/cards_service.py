"""Cards mutations/queries/drafts. Core owns hierarchy and project selection."""

from PySide6.QtCore import QObject, Signal

from lodandsy.application.entity_session import EntitySession
from lodandsy.application.field_edits import FieldEdits
from lodandsy.domain.card import EMPTY_DOCUMENT, Card
from lodandsy.domain.card_collection import CardCollection
from lodandsy.domain.card_schema import CARD_TYPES, FIELD_DEFINITIONS
from lodandsy.domain.entity_reference import ReferenceInfo


class CardsService(QObject):
    field_draft_changed = Signal(str, object)
    current_card_changed = Signal(object)
    card_created = Signal(str)
    card_changed = Signal(str, object)
    cards_deleted = Signal(object)
    cards_replaced = Signal()

    def __init__(self, cards=None, parent=None, *, core=None):
        super().__init__(parent)
        self.core = (
            core
            if core is not None
            else EntitySession(cards.entities if cards is not None else None, self)
        )
        self.cards = cards if cards is not None else CardCollection(entities=self.core.entities)
        self.field_drafts = {}
        from lodandsy.domain.card_schema import parse_field

        self.field_edits = FieldEdits(
            lambda key: self.cards.get(key[0]).value(key[1]),
            lambda key, value: self.update_card_fields(key[0], {key[1]: value}),
            lambda key, text: parse_field(key[1], text),
            self.field_drafts,
            self,
            lambda key, raw: self.set_field_draft(key[0], key[1], raw),
        )
        self._reference_cache = {}
        self.current_entity_changed = self.core.selection_changed
        self.entity_changed = self.core.entity_changed
        self.entity_created = self.core.entity_created
        self.entities_deleted = self.core.entities_deleted
        self.entities_replaced = self.core.replaced
        self.core.selection_changed.connect(
            lambda key: self.current_card_changed.emit(self.current_card_id)
        )
        self.core.entities_deleted.connect(self._deleted)
        self.core.replaced.connect(self._replaced)

    @property
    def entities(self):
        return self.core.entities

    @property
    def current_entity_id(self):
        return self.core.selected_id

    @property
    def current_entity(self):
        return self.entities.get(self.core.selected_id) if self.core.selected_id else None

    def select_entity(self, key):
        self.core.select(key)

    def clear_selection(self):
        self.core.select(None)

    def _deleted(self, keys):
        self.field_edits.clear(set(keys))
        for key in keys:
            self._reference_cache.pop(key, None)
        for identity in tuple(self.field_drafts):
            if identity[0] in keys:
                self.field_drafts.pop(identity, None)
        self.cards_deleted.emit(keys)

    def _replaced(self):
        self.field_edits.clear()
        self._reference_cache.clear()
        self.cards = CardCollection(entities=self.core.entities)
        self.field_drafts.clear()
        self.cards_replaced.emit()

    def replace_cards(self, cards):
        self.core.replace(cards.entities)

    def get_card(self, key):
        return self.cards.get(key)

    def all(self):
        return self.cards.all()

    def prepare_card(self, title, parent_id=None, *, card_type="note"):
        return Card(title, parent_id=parent_id, card_type=card_type)

    def reference_info(self, key):
        from lodandsy.application.rich_html import html_text

        card = self.cards.get(key)
        cached = self._reference_cache.get(key)
        if cached is not None and cached[0] is card:
            return cached[1]
        summary = card.value("summary") or ""
        previous = cached[0] if cached is not None else None
        if summary.strip():
            preview = " ".join(summary.split())
        elif (
            previous is not None
            and previous.sections == card.sections
            and not previous.value("summary")
        ):
            preview = cached[1].value("description_preview")
        else:
            preview = " ".join(html_text(card.content).split())
        if len(preview) > 240:
            preview = preview[:237] + "…"
        values = tuple(
            (name, card.value(name))
            for name in FIELD_DEFINITIONS
            if name not in {"description", "aliases"}
        )
        info = ReferenceInfo(
            card.id,
            "card",
            card.title,
            card_type=card.card_type,
            aliases=card.value("aliases") or (),
            image_id=card.portrait.asset_id if card.portrait else None,
            fields=(*values, ("description_preview", preview)),
        )
        self._reference_cache[key] = (card, info)
        return info

    @staticmethod
    def reference_types():
        return tuple((definition.title, key) for key, definition in CARD_TYPES.items())

    @staticmethod
    def projection_fields():
        return (
            ("Описание", "description_preview"),
            *(
                (definition.label, key)
                for key, definition in FIELD_DEFINITIONS.items()
                if key not in {"aliases", "description"}
            ),
        )

    def create_card(self, title, parent_id=None, *, card_type="note"):
        with self.core.transaction():
            card = self.cards.create(title, parent_id, card_type=card_type)
            self.core.after_commit(lambda: self.core.entity_created.emit(card.id))
            self.core.after_commit(lambda: self.card_created.emit(card.id))
            self.core.mark_changed()
        return card

    def update_card(self, card_id, **changes):
        with self.core.transaction():
            return self._update_card(card_id, **changes)

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
        self.field_edits.clear({key})
        for identity in tuple(self.field_drafts):
            if identity[0] == key:
                self.set_field_draft(key, identity[1], None)

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

    def _update_card(self, card_id: str, **changes: object) -> Card:
        previous = self.cards.get(card_id)
        if "content" in changes:
            from lodandsy.application.rich_html import validate_html

            validate_html(changes["content"])
        if "sections" in changes:
            from lodandsy.application.rich_html import validate_html

            previous_sections = {section.id: section for section in previous.sections}
            for section in changes["sections"]:
                old = previous_sections.get(section.id)
                if section.kind == "rich_text" and (old is None or old.content != section.content):
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
                self.core.after_commit(lambda: self.core.entity_changed.emit(card_id, structural))
            self.core.after_commit(lambda: self.card_changed.emit(card_id, fields))
            for removed in old_sections.keys() - new_sections.keys():
                self.field_drafts.pop((card_id, removed), None)
            self.core.mark_changed()
        return card

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
