import hashlib
import sqlite3
from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from lodandsy.application.sqlite_project_store import ProjectError, SQLiteProjectStore
from lodandsy.domain.actor_state import ActorRef
from lodandsy.domain.table_document import TablePayload

pytest_plugins = ["tests.project_fixture"]


def test_ac_automatically_uses_equipment_by_default(project):
    app, _ = project
    card = app.create_card("Новый персонаж", card_type="character")
    app.cards_service.update_card_fields(card.id, {"dexterity": 16})
    assert app.cards.get(card.id).value("ac_mode") == "auto"
    assert app.cards_service.effective(card.id).get("ac").value == 13
    definition = item(app)
    assert not app.cards_service.effective(definition.id).automatic
    assert app.cards_service.effective(definition.id).get("armor_ac").value == 14


def character(app, dex=16):
    card = app.create_card("Воин", card_type="character")
    app.cards_service.update_card_fields(card.id, {"dexterity": dex, "ac_mode": "auto"})
    section = next(s for s in card.sections if s.purpose == "inventory")
    return card, app.actions.section_table(card.id, section.id)


def item(app, kind="armor", category="medium", ac=14):
    card = app.create_card("Щит" if kind == "shield" else "Доспех", card_type="item")
    app.cards_service.update_card_fields(
        card.id,
        {
            "equipment_kind": kind,
            "armor_category": category,
            "armor_ac": ac,
        },
    )
    return card


def row(app, table_id, card, *, active=False, count=1):
    table = app.tables_service.get_table(table_id)
    record = table.new_row()
    app.tables_service.edit_table(table.id, rows=(*table.rows, record))
    columns = {c.key: c.id for c in table.columns}
    app.tables_service.set_cell(table.id, record.id, columns["item"], card.id)
    app.tables_service.set_cell(table.id, record.id, columns["quantity"], count, parsed=True)
    if active:
        app.actions.set_inventory_activity(table.id, record.id, True)
    return record.id


@pytest.mark.parametrize(
    "category,base,dex,result",
    [
        (None, None, 16, 13),
        ("light", 11, 16, 14),
        ("medium", 14, 16, 16),
        ("heavy", 16, 16, 16),
        ("heavy", 18, 16, 18),
        ("medium", 14, 8, 13),
        ("heavy", 16, 8, 16),
    ],
)
def test_armor_and_single_shield_matrix(project, category, base, dex, result):
    app, _ = project
    card, table = character(app, dex)
    if category:
        armor = item(app, category=category, ac=base)
        row(app, table.id, armor, active=True, count=8)
    assert app.cards_service.effective(card.id).get("ac").value == result
    shield = item(app, kind="shield")
    shield_row = row(app, table.id, shield, active=True, count=12)
    assert app.cards_service.effective(card.id).get("ac").value == result + 2
    app.actions.set_inventory_activity(table.id, shield_row, False)
    assert app.cards_service.effective(card.id).get("ac").value == result
    for retired in ("armor_type", "armor_base", "shield"):
        with pytest.raises(ValueError):
            app.cards_service.update_card_fields(card.id, {retired: True})


def test_duplicate_guards_all_mutations_cancel_replace_and_stale(project, monkeypatch):
    app, _ = project
    card, table = character(app)
    first, second = item(app), item(app, category="heavy", ac=18)
    a, b = row(app, table.id, first, active=True), row(app, table.id, second)
    before = app.tables_service.get_table(table.id)
    active = next(c for c in table.columns if c.key == "active")
    with pytest.raises(ValueError):
        app.tables_service.set_cell(table.id, b, active.id, True, parsed=True)
    candidate = before.with_cell(b, active.id, True)
    with pytest.raises(ValueError):
        with app.core.transaction():
            app.core.entities.put_payload(table.id, TablePayload(candidate.columns, candidate.rows))
    assert app.tables_service.get_table(table.id) == before
    view = app.tables.open_table(table.id).widget()
    column = [c.id for c in table.columns].index(active.id)
    with pytest.raises(ValueError):
        view.model.paste(view.model.index(1, column), "true")
    assert app.tables_service.get_table(table.id) == before
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    view.model.setData(
        view.model.index(1, column), Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole
    )
    assert app.tables_service.get_table(table.id) == before
    events = []
    app.core.committed.connect(lambda: events.append(1))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    view.model.setData(
        view.model.index(1, column), Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole
    )
    after = app.tables_service.get_table(table.id)
    assert [r.value(active.id) for r in after.rows] == [False, True] and events == [1]
    assert app.cards_service.effective(card.id).get("ac").value == 18
    guard = app.core.generation, app.core.serial
    app.cards_service.update_card_fields(first.id, {"armor_ac": 15})
    with pytest.raises(ValueError, match="изменились"):
        app.actions.set_inventory_activity(table.id, a, True, replace_existing=True, expected=guard)


def test_item_kind_mutation_cannot_create_two_armors(project):
    app, _ = project
    card, table = character(app)
    first, second = item(app), item(app, kind="item")
    row(app, table.id, first, active=True)
    row(app, table.id, second, active=True)
    with pytest.raises(ValueError):
        app.cards_service.update_card_fields(second.id, {"equipment_kind": "armor"})
    assert app.cards.get(second.id).value("equipment_kind") == "item"
    before = app.cards.get(second.id).payload()
    with pytest.raises(ValueError):
        with app.core.transaction():
            app.core.entities.put_payload(
                second.id,
                replace(
                    before,
                    values=tuple(
                        (k, "armor" if k == "equipment_kind" else v) for k, v in before.values
                    ),
                ),
            )


def test_actor_template_independence_live_item_manual_and_broken_ref(project):
    app, _ = project
    card, template = character(app)
    armor = item(app)
    row(app, template.id, armor, active=True)
    a, b = (app.cards_service.create_actor(card.id) for _ in range(2))
    assert app.cards_service.effective(a).get("ac").value == 16
    owned = app.tables_service.get_table(app.cards_service.get_actor(a).inventory_id)
    app.actions.set_inventory_activity(owned.id, owned.rows[0].id, False)
    assert app.cards_service.effective(a).get("ac").value == 13
    assert app.cards_service.effective(b).get("ac").value == 16
    app.cards_service.update_card_fields(armor.id, {"armor_ac": 15})
    assert app.cards_service.effective(b).get("ac").value == 17
    assert app.cards_service.effective(card.id).get("ac").value == 17
    app.cards_service.update_actor(b, {"ac_override": 21})
    app.actions.delete_entity(armor.id)
    assert app.cards_service.effective(b).get("ac").value == 21
    assert app.cards_service.effective(b).automatic["ac"].status == "incomplete"
    app.cards_service.update_actor(b, {"ac_override": None})
    assert app.cards_service.effective(b).get("ac").status == "incomplete"


def test_storage_profile_inputs_and_old_schema_readonly_rejection(project, tmp_path):
    app, project = project
    project.create_project(tmp_path / "Новый мир")
    card, table = character(app)
    row(app, table.id, item(app), active=True)
    ref = app.cards_service.create_actor(card.id)
    app.cards_service.update_card_fields(card.id, {"subclass": "Свой архетип"})
    preview = app.cards_service.preview_rules((("ac", "base_armor_base + dexterity_mod"),))
    app.cards_service.apply_rules(preview)
    assert app.cards_service.effective(ref).get("ac").value == 17
    assert project.save_current()
    expected = project.store.load()
    backup = tmp_path / "backup.lodbackup"
    project.store.backup(backup)
    restored = SQLiteProjectStore.restore(backup, tmp_path / "Копия")
    assert restored.load() == expected
    path = restored.path
    restored.close()
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=15")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ProjectError, match="Unsupported"):
        SQLiteProjectStore.open(path.parent)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert app.cards_service.get_actor(ActorRef(card.id, ref.actor_id)).id == ref.actor_id


def test_live_base_and_actor_breakdown_update_without_changing_ac(project):
    app, _ = project
    card, table = character(app, dex=10)
    armor = item(app)
    row(app, table.id, armor, active=True)
    editor = app.card_views.open_game_sheet(card.id).widget()
    binding = app.card_views.game_bindings[card.id]
    assert editor.game_sheet.results["ac"].text() == "14"
    binding.open_armor()
    app.cards_service.update_card_fields(
        armor.id, {"title": "Новая кираса", "armor_category": "light"}
    )
    assert "Новая кираса" in binding.armor_dialog.details.text()
    assert "Лёгкая" in binding.armor_dialog.details.text()
    ref = app.cards_service.create_actor(card.id)
    binding.select_actor(ref.actor_id)
    binding.open_armor()
    app.cards_service.update_card_fields(armor.id, {"armor_category": "heavy"})
    assert "Тяжёлая" in binding.armor_dialog.details.text()
    assert app.cards_service.effective(ref).get("ac").value == 14


def test_corrupt_saved_equipment_is_diagnosed_without_rewrite(project, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    card, table = character(app)
    row(app, table.id, item(app), active=True)
    second = row(app, table.id, item(app, category="heavy", ac=18))
    assert project.save_current()
    backup = tmp_path / "equipment.lodbackup"
    project.store.backup(backup)
    restored = SQLiteProjectStore.restore(backup, tmp_path / "corrupt")
    path = restored.path
    restored.close()
    active = next(c.id for c in table.columns if c.key == "active")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE table_cell SET value='true' WHERE table_id=? AND row_id=? AND column_id=?",
            (table.id, second, active),
        )
    before = path.read_bytes()
    with pytest.raises(ProjectError, match="доспехов"):
        SQLiteProjectStore.open(path.parent)
    assert path.read_bytes() == before


def test_subclass_homebrew_filter_keeps_existing_choice_after_reopen(project, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    card, _ = character(app)
    app.cards_service.update_card_fields(card.id, {"class_or_role": "Воин", "subclass": "Чемпион"})
    sheet = app.card_views.open_game_sheet(card.id).widget().game_sheet
    assert "Чемпион" in sheet.header.controls["subclass"].options
    app.cards_service.update_card_fields(card.id, {"class_or_role": "Волшебник"})
    assert app.cards.get(card.id).value("subclass") == "Чемпион"
    assert sheet.header.warning.text()
    app.cards_service.update_card_fields(
        card.id, {"subclass": "Своя школа", "race": "Свой народ", "persuasion_proficiency": 2}
    )
    assert not sheet.header.warning.text()
    assert project.save_current()
    snapshot = project.store.load()
    reopened = next(c for c in snapshot.cards if c.id == card.id)
    assert (
        reopened.value("subclass"),
        reopened.value("race"),
        reopened.value("persuasion_proficiency"),
    ) == ("Своя школа", "Свой народ", 2)
