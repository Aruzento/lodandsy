from lodandsy.application.cards_service import CardsService
from lodandsy.ui.game_labels import field_label
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
        self._actor_ref = None
        self._feet_per_cell = None
        self.open_inventory = lambda key: None
        self.open_sheet = lambda card_id, actor_id=None: None
        inspector.sheet_requested.connect(
            lambda: (
                self.open_sheet(
                    self.current_card_id, self._actor_ref.actor_id if self._actor_ref else None
                )
                if self.current_card_id
                else None
            )
        )
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
        inspector.base_requested.connect(self.show_base)
        inspector.inventory_requested.connect(self.show_inventory)
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
        self.session.cards_replaced.connect(self._reset_context)
        self.session.actor_changed.connect(self._on_actor_changed)
        self.session.rules_changed.connect(self._metadata)
        self.inspector.fields_changed.connect(self._on_fields)
        self.inspector.add_field_requested.connect(self._add_field)
        self.inspector.discard_drafts_requested.connect(self._discard)
        self.session.field_draft_changed.connect(self._on_card_changed)

        self.refresh()

    @property
    def current_entity(self):
        if self._actor_ref is not None:
            try:
                self.session.get_actor(self._actor_ref)
                return self.session.entities.get(self._actor_ref.card_id)
            except ValueError:
                self._actor_ref = None
        return self.session.current_entity

    @property
    def current_entity_id(self):
        entity = self.current_entity
        return entity.id if entity else None

    @property
    def current_card_id(self):
        entity = self.current_entity
        return entity.id if entity and entity.kind == "card" else None

    def address(self, field):
        if self._actor_ref is not None:
            from lodandsy.domain.actor_state import ValueAddress

            return ValueAddress(self._actor_ref.card_id, field, self._actor_ref.actor_id)
        return self.current_card_id, field

    def show_actor(self, reference, *, feet_per_cell=None):
        self.inspector.clear_feature_page()
        self.finish_edits()
        self.session.get_actor(reference)
        self._actor_ref = reference
        self._feet_per_cell = feet_per_cell
        self.refresh()

    def update_actor_scale(self, reference, scale):
        if self._actor_ref == reference:
            self._feet_per_cell = scale
            self._metadata()

    def show_base(self):
        key = self.current_card_id
        self.finish_edits()
        self._actor_ref = None
        if key:
            self.session.select_card(key)
        self.refresh()

    def show_inventory(self):
        if self._actor_ref:
            key = self.session.get_actor(self._actor_ref).inventory_id
            if key:
                self.open_inventory(key)

    def _reset_context(self):
        self.inspector.clear_feature_page()
        self._actor_ref = None
        self._field_owners.clear()
        self._title_owner = None
        self.refresh()

    def _on_actor_changed(self, card_id, actor_id, fields):
        if self._actor_ref and (self._actor_ref.card_id, self._actor_ref.actor_id) == (
            card_id,
            actor_id,
        ):
            self._metadata()

    def refresh(self) -> None:
        if self.inspector.feature_page_active:
            return
        card = self.current_entity

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
        actor_id = self._actor_ref.actor_id if self._actor_ref else None
        text = next(
            (
                message
                for address, message in errors.items()
                if address[0] == card.id and getattr(address, "actor_id", None) == actor_id
            ),
            "",
        )
        from lodandsy.ui.game_labels import error_text

        self.inspector.validation_notice.setText(error_text(text))
        self.inspector.validation_notice.setVisible(bool(text))
        self._sync_conflicts()

    def _sync_conflicts(self):
        key = self.current_entity_id
        manager = self.session.field_edits if self.current_card_id else self.title_edits
        self.inspector.conflicts.set_conflicts(
            [
                (
                    identity,
                    "Конфликт · " + field_label(identity[1]),
                    manager.drafts.get(identity, conflict.raw),
                    manager.read(identity),
                )
                for identity, conflict in manager.conflicts.items()
                if identity[0] == key
                and getattr(identity, "actor_id", None)
                == (self._actor_ref.actor_id if self._actor_ref else None)
            ]
            if manager and key
            else []
        )

    def _resolve_conflict(self, key, mine):
        manager = self.session.field_edits if self.current_card_id else self.title_edits
        if manager and key:
            manager.resolve(key, mine=mine)
            self.refresh()

    def _begin_field(self, field):
        key = self.current_card_id
        if key and not self.session.field_edits.has(self._field_owners.get(field)):
            self._field_owners[field] = self.session.field_edits.begin(self.address(field))

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
        entity = self.current_entity
        if entity is None:
            return
        manager = self.session.field_edits if entity.kind == "card" else self.title_edits
        if manager is not None and not manager.has(self._title_owner):
            self._title_manager = manager
            self._title_owner = manager.begin(
                self.address("actor_name") if self._actor_ref else (entity.id, "title")
            )

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
        entity = self.current_entity
        if entity and entity.kind == "card":
            card = self.session.cards.get(entity.id)
            if self._actor_ref:
                actor = self.session.get_actor(self._actor_ref)
                drafts = {
                    (actor.id, key[1]): value
                    for key, value in self.session.field_drafts.items()
                    if getattr(key, "actor_id", None) == actor.id and key[0] == card.id
                }
                self.inspector.set_actor_metadata(card, actor, drafts)
                raw = self.session.field_drafts.get(self.address("actor_name"), actor.name)
                self.inspector.title_edit.set_value(raw, force=not self.inspector.title_active())
            else:
                self.inspector.set_metadata(card, self.session.field_drafts)
            if self._actor_ref:
                self.inspector.set_effective(
                    self.session.effective(self._actor_ref or card.id),
                    card.card_type,
                    feet_per_cell=self._feet_per_cell if self._actor_ref else None,
                )
            self._sync_conflicts()
        else:
            self.inspector.clear_metadata()

    def _discard(self):
        if self.current_card_id:
            actor_id = self._actor_ref.actor_id if self._actor_ref else None
            keys = [
                key
                for key in self.session.field_drafts
                if key[0] == self.current_card_id and getattr(key, "actor_id", None) == actor_id
            ]
            self.session.field_edits.discard_keys(keys)
        elif self.current_entity_id and self.title_edits:
            self.title_edits.discard({self.current_entity_id})
        self.refresh()

    def _add_field(self):
        from PySide6.QtWidgets import QInputDialog

        from lodandsy.domain.card_schema import available_fields
        from lodandsy.ui.game_labels import field_label, field_surface

        key = self.current_card_id
        if not key or self._actor_ref:
            return
        fields = [
            f
            for f in available_fields(self.session.cards.get(key))
            if field_surface(f.key) == "inspector"
        ]
        if not fields:
            return
        labels = [field_label(f.key) for f in fields]
        label, ok = QInputDialog.getItem(self.inspector, "Поле", "Добавить:", labels, 0, False)
        if ok:
            self.session.add_card_field(key, fields[labels.index(label)].key)

    def _on_fields(self, key, changes):
        if key == self.current_card_id:
            try:
                if self._actor_ref:
                    self.session.update_actor(self._actor_ref, changes)
                elif "player" in changes:
                    from PySide6.QtWidgets import QDialog

                    from lodandsy.ui.player_dialog import PlayerDialog

                    enabled = changes["player"]
                    dialog = PlayerDialog(self.session.get_card(key), enabled, self.inspector)
                    if dialog.exec() == QDialog.DialogCode.Accepted:
                        actor_id = dialog.choice.currentData()
                        self.session.set_player(
                            key, enabled, actor_id=actor_id, create=enabled and actor_id is None
                        )
                    self._metadata()
                    return
                else:
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
        self.inspector.clear_feature_page()
        self.finish_edits()
        self._actor_ref = None
        self.refresh()

    def _on_title_changed(
        self,
        card_id: str,
        title: str,
    ) -> None:
        if card_id != self.current_entity_id:
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
        if card_id != self.current_entity_id:
            return

        resolved_parent_id = self._optional_card_id(parent_id)

        self.update_entity(card_id, parent_id=resolved_parent_id)

    def _on_structure_changed(self, _ids: object) -> None:
        self.refresh()

    def _on_card_changed(self, card_id: str, fields: frozenset[str]) -> None:
        if fields & {"title", "parent_id"}:
            self.refresh()
        elif card_id == self.current_card_id:
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
