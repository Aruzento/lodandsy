from lodandsy.application.cards_service import CardsService
from lodandsy.ui.inspector_panel import InspectorPanel


class CardInspectorBinding:
    def __init__(
        self,
        session: CardsService,
        inspector: InspectorPanel,
        update_entity=None,
        title_edits=None,
    ) -> None:
        self.session = session
        self.inspector = inspector
        self.update_entity = update_entity or session.core.update
        self.title_edits = title_edits
        self._field_owners = {}
        self._title_owner = None
        self._title_manager = None
        inspector.conflicts.resolve_requested.connect(self._resolve_conflict)
        session.field_edits.changed.connect(lambda key: self._sync_conflicts())
        if title_edits:
            title_edits.changed.connect(lambda key: self._sync_conflicts())
        form = inspector.field_form
        form.edit_active = lambda field: session.field_edits.has(self._field_owners.get(field))
        inspector.title_active = lambda: (
            self._title_manager is not None and self._title_manager.has(self._title_owner)
        )
        form.edit_started.connect(self._begin_field)
        form.buffer_changed.connect(self._buffer_field)
        form.commit_requested.connect(self._commit_field)
        form.cancel_requested.connect(self._cancel_field)
        inspector.title_edit.edit_started.connect(self._begin_title)
        inspector.title_edit.buffer_changed.connect(self._buffer_title)
        inspector.title_edit.cancel_requested.connect(self._cancel_title)
        if title_edits is not None:
            title_edits.changed.connect(
                lambda key: self.refresh() if key[0] == session.current_entity_id else None
            )

        self.inspector.title_changed.connect(self._on_title_changed)
        self.inspector.parent_changed.connect(self._on_parent_changed)

        self.session.current_entity_changed.connect(self._on_current_card_changed)
        self.session.entity_changed.connect(self._on_card_changed)
        self.session.card_created.connect(self._on_structure_changed)
        self.session.cards_deleted.connect(self._on_structure_changed)
        self.session.card_changed.connect(self._on_card_changed)
        self.session.cards_replaced.connect(self.refresh)
        self.inspector.fields_changed.connect(self._on_fields)
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
        if card.kind != "card" and self.title_edits is not None:
            raw = self.title_edits.drafts.get((card.id, "title"), card.title)
            self.inspector.title_edit.set_value(raw, force=not self.inspector.title_active())
        errors = (
            self.session.field_edits.errors
            if card.kind == "card"
            else self.title_edits.errors
            if self.title_edits
            else {}
        )
        text = next((message for (key, field), message in errors.items() if key == card.id), "")
        self.inspector.validation_notice.setText(text)
        self.inspector.validation_notice.setVisible(bool(text))
        self._sync_conflicts()

    def _sync_conflicts(self):
        key = self.session.current_entity_id
        manager = self.session.field_edits if self.session.current_card_id else self.title_edits
        self.inspector.conflicts.set_conflicts(
            [
                (
                    identity,
                    "Конфликт · " + identity[1],
                    manager.drafts.get(identity, conflict.raw),
                    manager.read(identity),
                )
                for identity, conflict in manager.conflicts.items()
                if identity[0] == key
            ]
            if manager and key
            else []
        )

    def _resolve_conflict(self, key, mine):
        manager = self.session.field_edits if self.session.current_card_id else self.title_edits
        if manager and key:
            manager.resolve(key, mine=mine)
            self.refresh()

    def _begin_field(self, field):
        key = self.session.current_card_id
        if key and not self.session.field_edits.has(self._field_owners.get(field)):
            self._field_owners[field] = self.session.field_edits.begin((key, field))

    def _buffer_field(self, field, raw):
        self._begin_field(field)
        self.session.field_edits.text(self._field_owners.get(field), raw)

    def _commit_field(self, field, raw):
        self._buffer_field(field, raw)
        self.session.field_edits.commit(self._field_owners.pop(field, None), finish=True)
        self._metadata()

    def _cancel_field(self, field):
        self.session.field_edits.cancel(self._field_owners.pop(field, None))
        self._metadata()

    def _begin_title(self):
        entity = self.session.current_entity
        if entity is None:
            return
        manager = self.session.field_edits if entity.kind == "card" else self.title_edits
        if manager is not None and not manager.has(self._title_owner):
            self._title_manager = manager
            self._title_owner = manager.begin((entity.id, "title"))

    def _buffer_title(self, raw):
        self._begin_title()
        if self._title_manager:
            self._title_manager.text(self._title_owner, raw)

    def _cancel_title(self):
        if self._title_manager:
            self._title_manager.cancel(self._title_owner)
        self._title_owner = None
        self.refresh()

    def finish_edits(self):
        for owner in tuple(self._field_owners.values()):
            self.session.field_edits.commit(owner, finish=True)
        self._field_owners.clear()
        if self._title_manager:
            self._title_manager.commit(self._title_owner, finish=True)
        self._title_owner = None

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
        elif self.session.current_entity_id and self.title_edits:
            self.title_edits.discard({self.session.current_entity_id})
        self.refresh()

    def _add_field(self):
        from PySide6.QtWidgets import QInputDialog

        from lodandsy.domain.card_schema import available_fields

        key = self.session.current_card_id
        if not key:
            return
        fields = available_fields(self.session.cards.get(key))
        if not fields:
            return
        labels = [f.label for f in fields]
        label, ok = QInputDialog.getItem(self.inspector, "Поле", "Добавить:", labels, 0, False)
        if ok:
            self.session.add_card_field(key, fields[labels.index(label)].key)

    def _on_fields(self, key, changes):
        if key == self.session.current_card_id:
            try:
                self.session.update_card_fields(key, changes)
                for field in changes:
                    self.session.set_field_draft(key, field, None)
            except ValueError:
                from lodandsy.ui.card_fields import field_text

                for field, value in changes.items():
                    self.session.set_field_draft(key, field, field_text(value))

    def _on_current_card_changed(
        self,
        _card_id: object,
    ) -> None:
        self.finish_edits()
        self.refresh()

    def _on_title_changed(
        self,
        card_id: str,
        title: str,
    ) -> None:
        if card_id != self.session.current_entity_id:
            return

        self._buffer_title(title)
        if self._title_manager:
            self._title_manager.commit(self._title_owner, finish=True)
        else:
            self.update_entity(card_id, title=title)
        self._title_owner = None
        self.refresh()

    def _on_parent_changed(
        self,
        card_id: str,
        parent_id: object,
    ) -> None:
        if card_id != self.session.current_entity_id:
            return

        resolved_parent_id = self._optional_card_id(parent_id)

        self.update_entity(card_id, parent_id=resolved_parent_id)

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
