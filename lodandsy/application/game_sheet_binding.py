"""Cards-owned addressed form binding over the existing shared FieldEdits."""

from lodandsy.domain.actor_state import ActorRef, ValueAddress
from lodandsy.domain.card_schema import field_definition
from lodandsy.ui.game_labels import error_text, field_label


class GameSheetBinding:
    def __init__(self, service, sheet, card_id, open_inventory, *, open_base_inventory=None):
        self.service, self.sheet, self.card_id = service, sheet, card_id
        self.open_inventory = open_inventory
        self.open_base_inventory = open_base_inventory
        self.armor_dialog = None
        self.actor_id = None
        self.owners = {}
        self.disposed = False
        self.generation = service.core.generation
        sheet.edit_active = lambda key: service.field_edits.has(self.owners.get(key))
        sheet.context_requested.connect(self.select_actor)
        sheet.inventory_requested.connect(self.inventory)
        sheet.armor_requested.connect(self.open_armor)
        sheet.edit_started.connect(self.begin)
        sheet.buffer_changed.connect(self.buffer)
        sheet.commit_requested.connect(self.commit)
        sheet.cancel_requested.connect(self.cancel)
        sheet.values_changed.connect(self.change)
        sheet.conflicts.resolve_requested.connect(self.resolve)
        service.card_changed.connect(self._card_changed)
        service.actor_changed.connect(self._actor_changed)
        service.field_edits.changed.connect(self._edit_changed)
        service.rules_changed.connect(self.refresh)
        service.base_effective_changed.connect(self._base_effective_changed)
        self.refresh()

    def reference(self):
        return ActorRef(self.card_id, self.actor_id) if self.actor_id else self.card_id

    def address(self, key):
        actor = self.actor_id if field_definition(key).scope == "actor" else None
        return ValueAddress(self.card_id, key, actor)

    def allowed(self, key):
        return (field_definition(key).scope == "actor") == (self.actor_id is not None)

    def begin(self, key):
        if (
            not self.disposed
            and self.allowed(key)
            and not self.service.field_edits.has(self.owners.get(key))
        ):
            self.owners[key] = self.service.field_edits.begin(self.address(key))

    def buffer(self, key, raw):
        self.begin(key)
        self.service.field_edits.text(self.owners.get(key), raw)

    def commit(self, key, raw):
        if not self.allowed(key):
            return
        self.buffer(key, raw)
        self.service.field_edits.commit(self.owners.pop(key, None), finish=True)
        self.refresh()

    def cancel(self, key):
        self.service.field_edits.cancel(self.owners.pop(key, None))
        self.refresh()

    def finish(self):
        for owner in tuple(self.owners.values()):
            self.service.field_edits.commit(owner, finish=True)
        self.owners.clear()

    def select_actor(self, actor_id):
        self.finish()
        if self.armor_dialog:
            self.armor_dialog.close()
        if actor_id:
            self.service.get_actor(ActorRef(self.card_id, actor_id))
        self.actor_id = actor_id
        self.refresh()

    def open_armor(self):
        from lodandsy.ui.armor_details import ArmorDetails

        if self.armor_dialog is None:
            self.armor_dialog = ArmorDetails(self.sheet.resource_settings["ac"], self.sheet)
            self.armor_dialog.inventory_requested.connect(self.inventory)
            self.armor_dialog.finished.connect(self.finish_armor)
        self.refresh()
        self.armor_dialog.show()
        self.armor_dialog.raise_()

    def finish_armor(self):
        for key in ("ac", "ac_mode", "ac_override"):
            owner = self.owners.pop(key, None)
            if owner:
                self.service.field_edits.commit(owner, finish=True)

    def inventory(self):
        if self.actor_id:
            key = self.service.get_actor(self.reference()).inventory_id
            if key:
                self.open_inventory(key)
        elif self.open_base_inventory:
            self.open_base_inventory()

    def change(self, changes):
        from PySide6.QtWidgets import QDialog

        from lodandsy.ui.player_dialog import PlayerDialog

        for key, value in changes.items():
            if not self.allowed(key):
                continue
            if key == "player":
                dialog = PlayerDialog(self.service.get_card(self.card_id), value, self.sheet)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    actor_id = dialog.choice.currentData()
                    self.service.set_player(
                        self.card_id, value, actor_id=actor_id, create=value and actor_id is None
                    )
            else:
                self.begin(key)
                self.service.field_edits.text(
                    self.owners.get(key), str(value) if value is not None else ""
                )
                self.service.field_edits.commit(self.owners.pop(key, None), finish=True)
        self.refresh()

    def resolve(self, key, mine):
        self.service.field_edits.resolve(key, mine=mine)
        self.refresh()

    def refresh(self):
        if self.disposed or self.generation != self.service.core.generation:
            return
        card = self.service.get_card(self.card_id)
        if self.actor_id and not any(a.id == self.actor_id for a in card.actors):
            self.finish()
            self.actor_id = None
        actor = card.actor(self.actor_id) if self.actor_id else None
        drafts = {
            (actor.id if getattr(key, "actor_id", None) else card.id, key[1]): raw
            for key, raw in self.service.field_drafts.items()
            if key[0] == card.id and getattr(key, "actor_id", None) in {None, self.actor_id}
        }
        self.sheet.set_values(card, actor, self.service.effective(self.reference()), drafts)
        if self.armor_dialog:
            self.armor_dialog.render(
                card,
                actor,
                self.service.effective(self.reference()),
                self.service.calculation_inputs(card, actor),
            )
        edits = self.service.field_edits

        def relevant(key):
            return key[0] == card.id and getattr(key, "actor_id", None) == self.actor_id

        errors = [error_text(e) for key, e in edits.errors.items() if relevant(key)]
        self.sheet.notice.setText(errors[0] if errors else "")
        self.sheet.notice.setVisible(bool(errors))
        self.sheet.conflicts.set_conflicts(
            [
                (
                    key,
                    "Конфликт · " + field_label(key[1]),
                    edits.drafts.get(key, conflict.raw),
                    edits.read(key),
                )
                for key, conflict in edits.conflicts.items()
                if relevant(key)
            ]
        )

    def _card_changed(self, key, fields):
        if key == self.card_id:
            self.refresh()

    def _base_effective_changed(self, key):
        if key == self.card_id and self.actor_id is None:
            self.refresh()

    def _actor_changed(self, card_id, actor_id, fields):
        if card_id == self.card_id:
            self.refresh()

    def _edit_changed(self, key):
        if key[0] == self.card_id:
            self.refresh()

    def dispose(self):
        if not self.disposed:
            if self.armor_dialog:
                self.armor_dialog.close()
            self.finish()
            self.disposed = True
            for signal, callback in (
                (self.service.card_changed, self._card_changed),
                (self.service.actor_changed, self._actor_changed),
                (self.service.field_edits.changed, self._edit_changed),
                (self.service.rules_changed, self.refresh),
                (self.service.base_effective_changed, self._base_effective_changed),
            ):
                signal.disconnect(callback)
