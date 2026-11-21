from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from lodandsy.domain.actor_state import ActorRef, ValueAddress
from lodandsy.ui.rules_editor import RulesEditor

pytest_plugins = ["tests.project_fixture"]


def test_actor_native_edit_context_drafts_and_relations(project, qtbot):
    app, controller = project
    card = app.create_card("Player", card_type="character", player=True)
    app.cards_service.update_card_fields(card.id, {"hp_max": 100, "speed_mode": "auto"})
    ref = ActorRef(card.id, card.default_actor_id)
    app.cards_service.update_actor(ref, {"hp_current": 70})
    editor = app.open_card_editor(card.id).widget()
    relations = next(s for s in card.sections if s.purpose == "relations")
    editor.select_section(relations.id)
    assert editor.relations.rows[ref.actor_id].text(0) == "Player №1"
    app.inspector_binding.show_actor(ref, feet_per_cell=5)
    panel = app.window.inspector_panel
    panel.details_tabs.setCurrentIndex(0)
    hp = panel.field_form.controls["hp_current"]
    app.window.show()
    app.window.raise_()
    app.window.activateWindow()
    qtbot.waitExposed(app.window)
    qtbot.waitUntil(app.window.isActiveWindow)
    hp.setFocus()
    qtbot.waitUntil(hp.hasFocus)
    hp.selectAll()
    qtbot.keyClicks(hp, "50")
    assert app.cards_service.get_actor(ref).value("hp_current") == 70
    qtbot.keyClick(hp, Qt.Key.Key_Return)
    assert app.cards_service.get_actor(ref).value("hp_current") == 50
    assert panel.field_form.controls["hp_current"] is hp
    assert "6 клеток" in panel.effective_labels["speed"].toolTip()
    address = ValueAddress(card.id, "hp_current", ref.actor_id)
    other = app.cards_service.field_edits.begin(address)
    app.cards_service.field_edits.text(other, "40")
    hp.selectAll()
    qtbot.keyClicks(hp, "45")
    assert hp.text() == "45"
    assert app.cards_service.field_edits.has(app.inspector_binding._field_owners["hp_current"])
    app.cards_service.field_edits.commit(other, finish=True)
    qtbot.keyClick(hp, Qt.Key.Key_Return)
    assert app.cards_service.get_actor(ref).value("hp_current") == 40
    assert address in app.cards_service.field_edits.conflicts, (
        hp.text(),
        app.cards_service.field_edits.errors,
        app.cards_service.field_drafts,
        app.inspector_binding._field_owners,
    )
    app.inspector_binding.show_base()
    app.inspector_binding.show_actor(ref)
    assert panel.field_form.controls["hp_current"].text() == "45"
    app.cards_service.field_edits.resolve(address, mine=False)
    app.inspector_binding.show_actor(ref)
    assert panel.field_form.controls["hp_current"].text() == "40"
    assert controller.draft_count == 0


def test_item_modifier_editor_and_formula_preview_are_local_until_apply(project, qtbot):
    app, _ = project
    item = app.create_card("Amulet", card_type="item")
    app.cards_service.select_card(item.id)
    panel = app.window.inspector_panel
    panel.details_tabs.setCurrentIndex(2)
    panel.modifiers.add_modifier()
    assert app.cards.get(item.id).value("modifiers") == ()
    panel.modifiers.apply.click()
    assert app.cards.get(item.id).value("modifiers")[0].target == "constitution"
    widget = RulesEditor(app.cards_service, app.window)
    qtbot.addWidget(widget)
    widget.target.setCurrentText("initiative")
    widget.expression.setPlainText("dexterity_mod + 7")
    before = app.cards_service.rules
    widget.check_project()
    assert app.cards_service.rules == before and widget.preview is not None
    widget.apply_project()
    assert dict(app.cards_service.rules.overrides)["initiative"] == "dexterity_mod + 7"
    widget.reset_formula()
    assert dict(app.cards_service.rules.overrides)["initiative"] == "dexterity_mod + 7"
    widget.check_project()
    app.cards_service.update_card_fields(item.id, {"summary": "concurrent"})
    widget.apply_project()
    assert "Preview" in widget.status.text()


def test_player_toggle_cancel_and_generic_current_above_max(project, monkeypatch):
    app, _ = project
    card = app.create_card("NPC", card_type="creature")
    app.cards_service.select_card(card.id)
    monkeypatch.setattr(
        "lodandsy.ui.player_dialog.PlayerDialog.exec", lambda self: QDialog.DialogCode.Rejected
    )
    app.inspector_binding._on_fields(card.id, {"player": True})
    assert not app.cards.get(card.id).value("player")
    assert app.cards.get(card.id).actors == ()
    app.cards_service.update_card_fields(card.id, {"hp_max": 20})
    ref = app.cards_service.create_actor(card.id)
    actor = app.cards_service.get_actor(ref)
    with pytest.raises(ValueError):
        with app.core.transaction():
            app.core.entities.put_payload(
                card.id,
                replace(
                    app.cards.get(card.id).payload(),
                    actors=(actor.with_fields({"hp_current": 21}),),
                ),
            )
    assert app.cards_service.get_actor(ref).value("hp_current") == 20


def test_preview_names_affected_values_and_delete_lists_participants(project):
    app, _ = project
    card = app.create_card("Player", card_type="character", player=True)
    preview = app.cards_service.preview_rules((("initiative", "dexterity_mod + 7"),))
    effects = app.cards_service.preview_effects(preview)
    assert any(row[1:3] == ("Player №1", "initiative") for row in effects)
    details = app.actions.deletion_details({card.id})
    assert "Player №1" in details and "инвентарей: 1" in details
    assert app.cards_service.rules.revision == 0
