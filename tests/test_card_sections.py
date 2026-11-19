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
    section = app.session.add_section(card.id, "Custom")
    editor.select_section(section.id)
    editor.text_edit.insertPlainText("Original")
    document = editor.text_edit.document()
    assert html_text(app.cards.get(card.id).section(section.id).content).strip() == "Original"
    app.session.update_section(card.id, section.id, title="Renamed")
    assert editor.text_edit.document() is document and document.isUndoAvailable()
    editor.text_edit.undo()
    assert not html_text(app.cards.get(card.id).section(section.id).content).strip()
    editor.text_edit.redo()
    inventory = next(s for s in app.cards.get(card.id).sections if s.purpose == "inventory")
    table = app.session.section_table(card.id, inventory.id)
    assert app.session.section_table(card.id, inventory.id).id == table.id
    assert app.session.entities.get(table.id).parent_id == card.id
    assert [c.name for c in table.columns] == ["Предмет", "Количество", "Описание"]
    editor.select_section(inventory.id)
    embedded = editor._embedded_tables[inventory.id]
    separate = app.modules.open_table(table.id).widget()
    separate.add_row()
    assert embedded.model.rowCount() == 1
    assert embedded.model.setData(embedded.model.index(0, 0), "Sword")
    assert separate.model.data(separate.model.index(0, 0)) == "Sword"
    assert separate.model.setData(separate.model.index(0, 1), "2")
    assert embedded.model.data(embedded.model.index(0, 1)) == "2"
    assert project.save_current()
    backup = tmp_path / "backup.lodbackup"
    project.store.backup(backup)
    restored = SQLiteProjectStore.restore(backup, tmp_path / "restore")
    assert restored.load() == project.store.load()
    restored.close()
    app.session.update_entity(table.id, parent_id=None)
    assert editor.body.currentIndex() == 1 and inventory.id not in editor._embedded_tables
    app.session.update_entity(table.id, parent_id=card.id)
    editor.select_section(inventory.id)
    assert inventory.id in editor._embedded_tables
    app.session.delete_section(card.id, inventory.id)
    assert app.modules.session.get_table(table.id)
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
