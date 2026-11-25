import pytest
from PySide6.QtCore import Qt

from lodandsy.domain.card_schema import ABILITIES, SKILLS
from lodandsy.domain.equipment import EquipmentEntry, resolve_equipment

pytest_plugins = ["tests.project_fixture"]


def test_one_row_per_save_skill_and_three_states(project):
    app, _ = project
    card = app.create_card("Навыки", card_type="character")
    app.cards_service.update_card_fields(card.id, {"charisma": 13, "level": 5})
    sheet = app.card_views.open_game_sheet(card.id).widget().game_sheet
    rows = {key: row for tile in sheet.tiles.values() for key, row in tile.rows.items()}
    assert set(rows) == set(SKILLS) | {a + "_save" for a in ABILITIES}
    row = rows["persuasion"]
    for expected, state in (("+1", 0), ("+4", 1), ("+7", 2), ("+1", 0)):
        assert row.result.text() == expected
        assert app.cards.get(card.id).value("persuasion_proficiency") == state
        row.toggle.click()
    save = rows["charisma_save"]
    assert save.result.text() == "+1"
    save.toggle.click()
    assert save.result.text() == "+4"


def test_inline_score_keeps_focus_draft_and_updates_dependents(project, qtbot):
    app, _ = project
    card = app.create_card("Ловкость", card_type="character")
    app.cards_service.update_card_fields(card.id, {"dexterity": 14, "ac_mode": "auto"})
    sheet = app.card_views.open_game_sheet(card.id).widget().game_sheet
    app.window.show()
    app.window.activateWindow()
    edit = sheet.tiles["dexterity"].edit
    edit.setFocus()
    qtbot.waitUntil(edit.hasFocus)
    edit.selectAll()
    qtbot.keyClicks(edit, "16")
    assert app.cards.get(card.id).value("dexterity") == 14
    qtbot.keyClick(edit, Qt.Key.Key_Return)
    assert app.cards.get(card.id).value("dexterity") == 16
    assert edit.hasFocus() and edit.text() == "16"
    assert sheet.tiles["dexterity"].result.text() == "+3"
    assert sheet.tiles["dexterity"].rows["acrobatics"].result.text() == "+3"
    assert sheet.results["initiative"].text() == "+3"
    assert sheet.results["ac"].text() == "13"
    edit.selectAll()
    qtbot.keyClicks(edit, "bad")
    qtbot.keyClick(edit, Qt.Key.Key_Escape)
    assert edit.text() == "16" and app.cards.get(card.id).value("dexterity") == 16


def test_inventory_navigation_creates_only_on_explicit_request(project):
    app, _ = project
    card = app.create_card("Шаблон", card_type="character")
    editor = app.card_views.open_game_sheet(card.id).widget()
    assert not app.cards.get(card.id).actors
    assert all(s.table_id is None for s in app.cards.get(card.id).sections)
    editor.game_sheet.inventory.click()
    section = next(s for s in app.cards.get(card.id).sections if s.purpose == "inventory")
    assert editor.current_section == section.id and section.table_id is None
    app.actions.section_table(card.id, section.id)
    assert app.cards.get(card.id).section(section.id).table_id
    assert not app.cards.get(card.id).actors


def test_equipment_facts_do_not_choose_first_or_invent_missing():
    armor = EquipmentEntry("row-a", "item-a", "Кираса", "armor", "medium", 14)
    shield = EquipmentEntry("row-s", "item-s", "Щит", "shield")
    facts = resolve_equipment((armor, shield))
    assert (facts.armor_type, facts.armor_base, facts.shield_bonus) == ("medium", 14, 2)
    assert resolve_equipment((armor, armor)).conflicts == ("row-a", "row-a")
    assert resolve_equipment((), missing=("item-missing",)).diagnostic
    for value in (True, float("nan"), -1, "2"):
        with pytest.raises(ValueError):
            EquipmentEntry("row-s", "item-s", "Щит", "shield", shield_bonus=value)


def test_header_homebrew_and_ac_dialog_keep_addressed_context(project):
    app, _ = project
    card = app.create_card("Хоумбрю", card_type="character")
    sheet = app.card_views.open_game_sheet(card.id).widget().game_sheet
    binding = app.card_views.game_bindings[card.id]
    race = sheet.header.controls["race"]
    race.input.setText("Свой народ")
    race.input.finish()
    assert app.cards.get(card.id).value("race") == "Свой народ"
    binding.open_armor()
    assert binding.armor_dialog.isVisible()
    assert "Базовая карточка" == binding.armor_dialog.context.text()
    binding.commit("ac_mode", "manual")
    binding.commit("ac", "21")
    assert binding.armor_dialog.result.text() == "КД 21"
    ref = app.cards_service.create_actor(card.id)
    binding.select_actor(ref.actor_id)
    assert not binding.armor_dialog.isVisible()
    binding.open_armor()
    assert ref.actor_id == binding.actor_id
    binding.commit("ac_override", "23")
    assert binding.armor_dialog.result.text() == "КД 23"
    assert app.cards.get(card.id).value("ac") == 21
