from lodandsy.application.application_session import ApplicationSession
from lodandsy.ui.inspector_panel import InspectorPanel


class CardInspectorBinding:
    def __init__(
        self,
        session: ApplicationSession,
        inspector: InspectorPanel,
    ) -> None:
        self.session = session
        self.inspector = inspector

        self.inspector.title_changed.connect(self._on_title_changed)
        self.inspector.parent_changed.connect(self._on_parent_changed)

        self.session.current_entity_changed.connect(self._on_current_card_changed)
        self.session.entity_changed.connect(self._on_card_changed)
        self.session.card_created.connect(self._on_structure_changed)
        self.session.cards_deleted.connect(self._on_structure_changed)
        self.session.card_changed.connect(self._on_card_changed)
        self.session.cards_replaced.connect(self.refresh)
        self.inspector.fields_changed.connect(self._on_fields)
        self.inspector.field_draft_changed.connect(self.session.set_field_draft)
        self.inspector.add_field_requested.connect(self._add_field)
        self.inspector.discard_drafts_requested.connect(self._discard)
        self.session.field_draft_changed.connect(self._on_card_changed)

        self.refresh()

    def refresh(self) -> None:
        card = self.session.current_entity

        if card is None:
            self.inspector.clear_card()
            return

        self.inspector.set_card(
            card_id=card.id,
            title=card.title,
            parent_id=card.parent_id,
            parent_options=self._build_parent_options(card.id),
        )
        self._metadata()

    def _metadata(self):
        entity = self.session.current_entity
        if entity and entity.kind == "card":
            self.inspector.set_metadata(
                self.session.cards.get(entity.id), self.session.field_drafts
            )
        else:
            self.inspector.clear_metadata()

    def _discard(self):
        if self.session.current_card_id:
            self.session.discard_field_drafts(self.session.current_card_id)

    def _add_field(self):
        from PySide6.QtWidgets import QInputDialog

        from lodandsy.domain.card_schema import FIELD_DEFINITIONS

        key = self.session.current_card_id
        if not key:
            return
        fields = [
            f
            for f in FIELD_DEFINITIONS.values()
            if f.group != "source" and f.key not in {"title", "description", "portrait"}
        ]
        labels = [f.label for f in fields]
        label, ok = QInputDialog.getItem(self.inspector, "Поле", "Добавить:", labels, 0, False)
        if ok:
            field = fields[labels.index(label)]
            self._on_fields(key, {field.key: field.default})

    def _on_fields(self, key, changes):
        if key == self.session.current_card_id:
            try:
                self.session.update_card_fields(key, changes)
            except ValueError:
                from lodandsy.ui.card_fields import field_text

                for field, value in changes.items():
                    self.session.set_field_draft(key, field, field_text(value))

    def _on_current_card_changed(
        self,
        _card_id: object,
    ) -> None:
        self.refresh()

    def _on_title_changed(
        self,
        card_id: str,
        title: str,
    ) -> None:
        if card_id != self.session.current_entity_id:
            return

        if self.session.current_entity.kind == "card":
            self.session.set_field_draft(card_id, "title", None)
            self.session.update_card_fields(card_id, {"title": title})
        else:
            self.session.update_entity(card_id, title=title)

    def _on_parent_changed(
        self,
        card_id: str,
        parent_id: object,
    ) -> None:
        if card_id != self.session.current_entity_id:
            return

        resolved_parent_id = self._optional_card_id(parent_id)

        self.session.update_entity(card_id, parent_id=resolved_parent_id)

    def _on_structure_changed(self, _ids: object) -> None:
        self.refresh()

    def _on_card_changed(self, card_id: str, fields: frozenset[str]) -> None:
        if fields & {"title", "parent_id"}:
            self.refresh()
        elif card_id == self.session.current_card_id:
            self._metadata()

    def _build_parent_options(
        self,
        card_id: str,
    ) -> list[tuple[str | None, str]]:
        blocked_ids = {
            card_id,
            *self.session.entities.descendant_ids(card_id),
        }

        options: list[tuple[str | None, str]] = [(None, "Корень проекта")]

        for card in self.session.entities.summaries():
            if card.id in blocked_ids:
                continue

            options.append(
                (
                    card.id,
                    card.title,
                )
            )

        return options

    @staticmethod
    def _optional_card_id(
        value: object,
    ) -> str | None:
        if value is None:
            return None

        if isinstance(value, str):
            return value

        raise TypeError("Card id must be str or None")
