import json
from dataclasses import asdict

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox, QPlainTextEdit

from lodandsy.domain.actor_state import ValueAddress
from lodandsy.domain.card_schema import FIELD_DEFINITIONS, permitted_fields
from lodandsy.domain.modifiers import Modifier
from lodandsy.ui.card_document_state import CardDocumentState
from lodandsy.ui.game_labels import ATTRIBUTES_PAGE, MODIFIERS_PAGE, field_label, field_surface
from lodandsy.ui.hit_history import HitHistoryEdit
from lodandsy.ui.modifier_editor import ModifierDialog

pytest_plugins = ["tests.project_fixture"]


@pytest.mark.parametrize("card_type", ["character", "creature", "object", "item"])
def test_virtual_page_is_single_stable_and_not_a_saved_section(project, card_type):
    app, _ = project
    card = app.create_card("До изменения интерфейса", card_type=card_type)
    original = card.payload()
    editor = app.open_card_editor(card.id).widget()
    key = MODIFIERS_PAGE if card_type == "item" else ATTRIBUTES_PAGE
    for _ in range(3):
        app.cards_service.update_card_fields(card.id, {"summary": "Обновлено"})
        editor.set_canonical(app.cards.get(card.id))
        keys = [editor.section_bar.tabData(i) for i in range(editor.section_bar.count())]
        assert keys.count(key) == 1
        editor.select_section(key)
    assert app.cards.get(card.id).sections == original.sections
    assert not app.cards.get(card.id).actors
    preferences = editor.document_state.ui_values()
    state = CardDocumentState(card.content, app.window, card.sections[0].id)
    state.load_ui_values(preferences)
    assert state.active_section == key
    app.window_manager.close_window(app.card_editor_window_key(card.id))
    reopened = app.open_card_editor(card.id).widget()
    assert reopened.current_section == key
    assert app.cards.get(card.id).sections == original.sections


def test_base_no_actor_tiles_and_all_fields_have_a_surface(project):
    app, _ = project
    card = app.create_card("База", card_type="character")
    app.cards_service.update_card_fields(
        card.id, {"strength": 8, "dexterity": 10, "constitution": 12, "charisma": 16}
    )
    editor = app.card_views.open_game_sheet(card.id).widget()
    sheet = editor.game_sheet
    assert [
        sheet.tiles[key].result.text()
        for key in ("strength", "dexterity", "constitution", "charisma")
    ] == ["−1 (8)", "+0 (10)", "+1 (12)", "+3 (16)"]
    assert "Максимум" in sheet.results["hp_max"].text()
    assert "hp_current" not in sheet.controls
    assert app.cards.get(card.id).actors == ()
    base_keys = {key for key in sheet.controls if FIELD_DEFINITIONS[key].scope == "card"}
    wanted = {key for key in permitted_fields(card.card_type) if field_surface(key) == "attributes"}
    assert wanted <= base_keys
    assert not set(app.window.inspector_panel.field_form.controls) & wanted
    for key in FIELD_DEFINITIONS:
        assert field_surface(key) in {
            "document",
            "data-only",
            "attributes",
            "modifiers",
            "item",
            "inspector",
        }
        assert field_label(key)


def test_sheet_item_source_recalculates_hp_without_healing_and_clamps(project):
    app, _ = project
    card = app.create_card("Воин", card_type="character")
    app.cards_service.update_card_fields(
        card.id,
        {
            "level": 5,
            "constitution": 14,
            "hit_die": 10,
            "hp_gains": (10, 6, 6, 6, 6),
            "hp_max_mode": "auto",
        },
    )
    ref = app.cards_service.create_actor(card.id)
    sheet = app.card_views.open_game_sheet(card.id, ref.actor_id).widget().game_sheet
    assert sheet.tiles["constitution"].result.text() == "+2 (14)"
    assert sheet.results["hp_max"].text() == "44 / 44"
    item = app.create_card("Амулет", card_type="item")
    app.cards_service.update_card_fields(
        item.id,
        {
            "modifiers": (Modifier("constitution", operand=2),),
        },
    )
    table = app.tables_service.get_table(app.cards_service.get_actor(ref).inventory_id)
    row = table.new_row()
    app.tables_service.edit_table(table.id, rows=(row,))
    columns = {c.key: c.id for c in table.columns}
    app.tables_service.set_cell(table.id, row.id, columns["item"], item.id)
    app.tables_service.set_cell(table.id, row.id, columns["active"], True, parsed=True)
    assert sheet.tiles["constitution"].result.text() == "+3 (16)"
    assert sheet.results["hp_max"].text() == "44 / 49"
    assert "Амулет" in sheet.sources.text()
    app.cards_service.update_actor(ref, {"hp_current": 49})
    app.tables_service.set_cell(table.id, row.id, columns["active"], False, parsed=True)
    assert sheet.results["hp_max"].text() == "44 / 44"
    binding = app.card_views.game_bindings[card.id]
    binding.select_actor(None)
    binding.commit("hp_max_mode", "manual")
    binding.commit("hp_max", "0")
    binding.select_actor(ref.actor_id)
    assert sheet.hp_progress.value() == 0
    assert sheet.results["hp_max"].text() == "0 / 0"


def test_native_history_explicit_accept_cancel_and_bad_ui_preference(qtbot):
    control = HitHistoryEdit()
    qtbot.addWidget(control)
    control.level, control.die = 2, 10
    control.set_value("10, 6")
    changes = []
    control.commit_requested.connect(changes.append)

    def accept():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QDialog)
        edits = dialog.findChildren(QLineEdit)
        assert len(edits) == 2
        edits[1].setText("7")
        dialog.accept()

    QTimer.singleShot(0, accept)
    control.open_editor()
    assert changes == ["10, 7"]
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
    control.open_editor()
    assert changes == ["10, 7"] and control.raw == "10, 7"
    from lodandsy.domain.card import EMPTY_DOCUMENT

    state = CardDocumentState(EMPTY_DOCUMENT, control)
    state.load_ui_values({"active_section": ["invalid"]})
    assert state.active_section is None


def test_actor_context_routes_drafts_and_shared_map_inspector(project):
    app, _ = project
    card = app.create_card("Гоблин", card_type="creature")
    app.cards_service.update_card_fields(card.id, {"hp_max": 20})
    a, b = [app.cards_service.create_actor(card.id) for _ in range(2)]
    editor = app.card_views.open_game_sheet(card.id, a.actor_id).widget()
    binding = app.card_views.game_bindings[card.id]
    binding.buffer("hp_current", "7")
    assert app.cards_service.get_actor(a).value("hp_current") == 20
    binding.commit("hp_current", "7")
    assert app.cards_service.get_actor(a).value("hp_current") == 7
    assert app.cards_service.get_actor(b).value("hp_current") == 20
    binding.select_actor(b.actor_id)
    binding.commit("strength", "99")  # Disabled inherited controls cannot bypass addressing.
    assert app.cards.get(card.id).value("strength") == 10
    binding.commit("hp_current", "bad")
    address = ValueAddress(card.id, "hp_current", b.actor_id)
    assert app.cards_service.field_drafts[address] == "bad"
    binding.select_actor(a.actor_id)
    assert editor.game_sheet.controls["hp_current"].text() == "7"
    app.inspector_binding.show_actor(b)
    assert app.window.inspector_panel.field_form.controls["hp_current"].text() == "bad"
    binding.select_actor(b.actor_id)
    app.cards_service.field_edits.resolve(address, mine=False)
    assert editor.game_sheet.controls["hp_current"].text() == "20"


def test_actor_sheet_conflict_does_not_retarget_or_overwrite(project):
    app, _ = project
    card = app.create_card("Участник", card_type="creature")
    app.cards_service.update_card_fields(card.id, {"hp_max": 20})
    ref = app.cards_service.create_actor(card.id)
    app.card_views.open_game_sheet(card.id, ref.actor_id)
    binding = app.card_views.game_bindings[card.id]
    binding.buffer("hp_current", "7")
    app.cards_service.update_actor(ref, {"hp_current": 8})
    binding.commit("hp_current", "7")
    address = ValueAddress(card.id, "hp_current", ref.actor_id)
    assert address in app.cards_service.field_edits.conflicts
    assert app.cards_service.get_actor(ref).value("hp_current") == 8
    binding.select_actor(None)
    assert app.cards.get(card.id).value("hp_max") == 20
    binding.select_actor(ref.actor_id)
    assert binding.sheet.controls["hp_current"].text() == "7"
    assert app.cards_service.field_edits.resolve(address, mine=True)
    assert app.cards_service.get_actor(ref).value("hp_current") == 7


def test_real_sheet_width_reflows_after_layout_and_preserves_focus(project, qtbot):
    app, _ = project
    card = app.create_card("Ширина", card_type="character")
    dock = app.card_views.open_game_sheet(card.id)
    dock.dock.setFloating()
    app.window.show()
    floating = dock.dock.floatingDockContainer()
    sheet = dock.widget().game_sheet
    for width, columns in ((1040, 6), (660, 3), (400, 2)):
        floating.resize(width, 950)
        floating.show()
        qtbot.waitUntil(lambda: sheet._columns == columns)
        assert sheet.scroll.horizontalScrollBar().maximum() == 0
        rectangles = [sheet.ability_grid.cellRect(0, col) for col in range(columns)]
        assert all(rect.width() > 50 for rect in rectangles)
    assert app.cards.get(card.id).actors == ()


def test_modifier_catalog_form_uuid_cancel_and_conflict(project, monkeypatch):
    app, _ = project
    card = app.create_card("Амулет", card_type="item")
    modifier = Modifier("constitution", operand=2)
    app.cards_service.update_card_fields(card.id, {"modifiers": (modifier,)})
    page = app.card_views.open_game_sheet(card.id).widget().item_page
    dialog = ModifierDialog(asdict(modifier), page)
    dialog.search.setText("тело")
    assert dialog.target.count() >= 1
    assert not dialog.target.isEditable()
    dialog.target.setCurrentIndex(dialog.target.findData("constitution"))
    dialog.operand.setValue(3)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.data["id"] == modifier.id
    before = app.cards.get(card.id)
    monkeypatch.setattr(ModifierDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    page.modifiers.add_modifier()
    assert app.cards.get(card.id) == before
    assert len(json.loads(page.modifiers.raw())) == 1
    changed = asdict(modifier) | {"operand": 4}
    page.modifiers.raw_changed.emit(json.dumps([changed]))
    app.cards_service.update_card_fields(card.id, {"modifiers": (Modifier("strength", operand=1),)})
    page.modifiers.commit_requested.emit(json.dumps([changed]))
    assert (card.id, "modifiers") in app.cards_service.field_edits.conflicts
    assert app.cards.get(card.id).value("modifiers")[0].target == "strength"
    assert "{" not in page.conflicts.details.text()


def test_rules_gear_typed_example_errors_staleness_and_close(project, qtbot, monkeypatch, tmp_path):
    app, project_controller = project
    assert not app.rules_action.isEnabled()
    project_controller.create_project(tmp_path / "мир")
    app.cards_service.clear_selection()
    assert app.rules_action.isEnabled()
    widget = app.open_rules()
    assert app.open_rules() is widget
    assert not hasattr(app.window.inspector_panel, "rules_button")
    widget.search.setText("модификатор телосложения")
    assert not widget.items["constitution_mod"].isHidden()
    widget.select_formula("constitution_mod")
    widget.example_controls["constitution"].setText("16")
    widget.test_example()
    assert widget.status.text() == "Результат: 3"
    assert not any(
        control.toPlainText().startswith("{") for control in widget.findChildren(QPlainTextEdit)
    )
    old = app.cards_service.rules
    widget.expression.setPlainText("1 / 0")
    widget.check_project()
    assert widget.preview is None and not widget.apply.isEnabled()
    assert "ноль" in widget.status.text()
    widget.expression.setPlainText("floor((constitution - 10) / 2) + 1")
    widget.check_project()
    assert widget.preview is not None and app.cards_service.rules == old
    app.create_card("Конкурентная правка")
    assert not widget.apply.isEnabled() and widget.preview is None
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    widget.reject()
    assert widget.result() == 0 and app._rules_editor is widget
    assert app.cards_service.rules == old
    widget.close_for_project()
    assert app._rules_editor is None
