from lodandsy.application.cards_service import (
    CardsService,
)
from lodandsy.ui.card_editor import CardEditorWidget
from lodandsy.ui.game_labels import error_text, field_label


class CardEditorBinding:
    def __init__(
        self,
        session: CardsService,
        editor: CardEditorWidget,
        card_id: str,
    ) -> None:
        self.session = session
        self.editor = editor
        self.card_id = card_id
        self.session.cards.get(card_id)

        self._disposed = False
        self._field_owners = {}
        self.editor.item_page.settings = lambda: self.session.settings
        self.editor.field_active = lambda field: self.session.field_edits.has(
            self._field_owners.get(field)
        )
        self.editor.field_edit_started.connect(self._begin_field)
        self.editor.field_buffer_changed.connect(self._buffer_field)
        self.editor.field_commit_requested.connect(self._commit_field)
        self.editor.field_cancel_requested.connect(self._cancel_field)

        self.editor.conflicts.resolve_requested.connect(self._resolve_conflict)
        self.editor.item_page.conflicts.resolve_requested.connect(self._resolve_conflict)
        self.session.field_edits.changed.connect(self._field_status)
        self.editor.content_changed.connect(self._on_content_changed)

        self.session.card_changed.connect(self._on_card_changed)
        self.editor.portrait_panel.changed.connect(self._on_portrait_changed)
        self.editor.discard_drafts_requested.connect(self._discard_drafts)
        self.session.field_draft_changed.connect(self._on_card_changed)
        self.session.cards_deleted.connect(self._on_cards_deleted)
        self.session.economy_changed.connect(self._economy_changed)

        self.refresh()

    @property
    def is_disposed(self) -> bool:
        return self._disposed

    def refresh(self, fields=None) -> None:
        if self._disposed:
            return

        card = self.session.cards.get(self.card_id)

        self.editor.set_canonical(card, self.session.field_drafts, fields=fields)
        edits = self.session.field_edits
        errors = [
            error_text(message)
            for key, message in edits.errors.items()
            if key[0] == self.card_id and getattr(key, "actor_id", None) is None
        ]
        if errors:
            self.editor.validation_status.setText(errors[0])
        self.editor.conflicts.set_conflicts(
            [
                (
                    key,
                    "Конфликт · " + field_label(key[1]),
                    edits.drafts.get(key, conflict.raw),
                    edits.read(key),
                )
                for key, conflict in edits.conflicts.items()
                if key[0] == self.card_id and key[1] in {"title", "summary"}
            ]
        )
        self.editor.item_page.conflicts.set_conflicts(
            [
                (
                    key,
                    "Конфликт · " + field_label(key[1]),
                    edits.drafts.get(key, conflict.raw),
                    edits.read(key),
                )
                for key, conflict in edits.conflicts.items()
                if key[0] == self.card_id
                and key[1]
                in {
                    "rarity",
                    "weight",
                    "cost",
                    "modifiers",
                    "equipment_kind",
                    "armor_category",
                    "armor_ac",
                    "shield_bonus",
                }
                and getattr(key, "actor_id", None) is None
            ]
        )

    def dispose(self) -> None:
        if self._disposed:
            return

        self.editor.flush_pending()
        self._disposed = True
        self.session.field_edits.changed.disconnect(self._field_status)
        for owner in tuple(self._field_owners.values()):
            self.session.field_edits.commit(owner, finish=True)
        self._field_owners.clear()
        self.editor.field_edit_started.disconnect(self._begin_field)
        self.editor.field_buffer_changed.disconnect(self._buffer_field)
        self.editor.field_commit_requested.disconnect(self._commit_field)
        self.editor.field_cancel_requested.disconnect(self._cancel_field)

        self.editor.content_changed.disconnect(self._on_content_changed)

        self.session.card_changed.disconnect(self._on_card_changed)
        self.session.cards_deleted.disconnect(self._on_cards_deleted)
        self.editor.portrait_panel.changed.disconnect(self._on_portrait_changed)
        self.editor.discard_drafts_requested.disconnect(self._discard_drafts)
        self.session.field_draft_changed.disconnect(self._on_card_changed)
        self.session.economy_changed.disconnect(self._economy_changed)

    def _economy_changed(self):
        if self.session.get_card(self.card_id).card_type == "item":
            self.refresh(frozenset({"cost", "item_category"}))

    def _on_cards_deleted(self, card_ids: tuple[str, ...]) -> None:
        if self.card_id in card_ids:
            self.editor.clear_card()
            self.dispose()

    def _on_card_changed(self, card_id: str, fields: frozenset[str]) -> None:
        if card_id == self.editor.card_id:
            self.refresh(fields)

    def _field_status(self, key):
        if key[0] == self.card_id:
            self.refresh(frozenset({key[1]}))

    def _resolve_conflict(self, key, mine):
        if key:
            self.session.field_edits.resolve(key, mine=mine)
            self.refresh(frozenset({key[1]}))

    def _begin_field(self, field):
        if not self._disposed and not self.session.field_edits.has(self._field_owners.get(field)):
            self._field_owners[field] = self.session.field_edits.begin((self.card_id, field))

    def _buffer_field(self, field, raw):
        self._begin_field(field)
        self.session.field_edits.text(self._field_owners.get(field), raw)

    def _commit_field(self, field, raw):
        self._buffer_field(field, raw)
        self.session.field_edits.commit(self._field_owners.pop(field, None), finish=True)
        self.refresh(frozenset({field}))

    def _cancel_field(self, field):
        self.session.field_edits.cancel(self._field_owners.pop(field, None))
        self.refresh(frozenset({field}))

    def _discard_drafts(self):
        self.session.discard_field_drafts(self.card_id)

    def _on_portrait_changed(self, portrait):
        if not self._disposed:
            self.session.update_card(self.card_id, portrait=portrait)

    def _on_content_changed(
        self,
        card_id: str,
        content: str,
    ) -> None:
        if self._disposed:
            return

        if card_id != self.card_id:
            return

        key = self.editor.current_section
        try:
            self.session.update_section(card_id, key, content=content)
        except ValueError as error:
            self.session.set_field_draft(card_id, key, content)
            self.editor.show_link_error(str(error))
            return
        self.session.set_field_draft(card_id, key, None)
        self.editor._content = content
        self.editor.text_edit.document().canonical_content = content
        self.editor.text_edit.document().pending_content = None
