from dataclasses import replace

import pytest

from lodandsy.application.rich_html import html_text
from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.domain.card import Card, CardSection

pytest_plugins = ["tests.project_fixture"]


def test_uuid_sections_rename_undo_and_inventory_shared_views(project, tmp_path, qtbot):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Character", card_type="character")
    editor = app.open_card_editor(card.id).widget()
    section = app.cards_service.add_section(card.id, "Custom")
    editor.select_section(section.id)
    editor.text_edit.insertPlainText("Original")
    editor.flush_pending()
    document = editor.text_edit.document()
    assert html_text(app.cards.get(card.id).section(section.id).content).strip() == "Original"
    app.cards_service.update_section(card.id, section.id, title="Renamed")
    assert editor.text_edit.document() is document and document.isUndoAvailable()
    editor.text_edit.undo()
    editor.flush_pending()
    assert not html_text(app.cards.get(card.id).section(section.id).content).strip()
    editor.text_edit.redo()
    inventory = next(s for s in app.cards.get(card.id).sections if s.purpose == "inventory")
    table = app.actions.section_table(card.id, inventory.id)
    assert app.actions.section_table(card.id, inventory.id).id == table.id
    assert app.cards_service.entities.get(table.id).parent_id == card.id
    assert [c.name for c in table.columns] == [
        "Предмет", "Количество", "Описание", "Стоимость", "Активен / надет"
    ]
    editor.select_section(inventory.id)
    embedded = editor._embedded_tables[inventory.id]
    separate = app.tables.open_table(table.id).widget()
    separate.add_row()
    assert embedded.model.rowCount() == 1
    sword = app.create_card("Sword", card_type="item")
    assert embedded.model.setData(embedded.model.index(0, 0), sword.id)
    assert separate.model.data(separate.model.index(0, 0)) == "Sword"
    assert separate.model.setData(separate.model.index(0, 1), "2")
    assert embedded.model.data(embedded.model.index(0, 1)) == "2"
    assert project.save_current()
    backup = tmp_path / "backup.lodbackup"
    project.store.backup(backup)
    restored = SQLiteProjectStore.restore(backup, tmp_path / "restore")
    assert restored.load() == project.store.load()
    restored.close()
    app.actions.update_entity(table.id, parent_id=None)
    assert editor.body.currentIndex() == 1 and inventory.id not in editor._embedded_tables
    app.actions.update_entity(table.id, parent_id=card.id)
    editor.select_section(inventory.id)
    assert inventory.id in editor._embedded_tables
    app.cards_service.delete_section(card.id, inventory.id)
    assert app.tables_service.get_table(table.id)
    app.window_manager.close_window(app.card_editor_window_key(card.id))
    reopened = app.open_card_editor(card.id).widget()
    reopened.select_section(section.id)
    assert reopened.text_edit.document() is document


def test_no_duplicate_section_ids_order_and_kind():
    card = Card("Card")
    with pytest.raises(ValueError):
        replace(card, sections=(card.sections[0], card.sections[0]))
    with pytest.raises(ValueError):
        CardSection("Bad", kind="unknown")
    with pytest.raises(ValueError):
        CardSection("Bad", kind="table_ref", content="copy")
