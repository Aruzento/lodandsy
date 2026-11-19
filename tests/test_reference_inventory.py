from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QAbstractItemModelTester

from lodandsy.application.rich_html import text_document
from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.domain.table_document import ColumnDefinition
from lodandsy.ui.entity_picker import EntityPicker

pytest_plugins = ["tests.project_fixture"]


def inventory(app):
    card = app.create_card("Владелец", card_type="character")
    section = next(s for s in card.sections if s.purpose == "inventory")
    table = app.actions.section_table(card.id, section.id)
    app.tables_service.edit_table(table.id, rows=(table.new_row(),))
    return card, section, app.tables_service.get_table(table.id)


def test_item_projections_are_live_addressed_and_never_stored(project, tmp_path, qtbot):
    app, project = project
    project.create_project(tmp_path / "Мир")
    owner, section, table = inventory(app)
    assert [c.name for c in table.columns] == ["Предмет", "Количество", "Описание", "Стоимость"]
    assert [c.key for c in table.columns] == ["item", "quantity", "description", "cost"]
    item = app.create_card("Меч", card_type="item")
    app.cards_service.update_card_fields(item.id, {"summary": "Острый", "cost": 0})
    editor = app.open_card_editor(owner.id).widget()
    editor.select_section(section.id)
    embedded = editor.table_layout.itemAt(0).widget()
    view = app.tables.open_table(table.id).widget()
    changes = []
    view.model.dataChanged.connect(lambda a, b, *roles: changes.append((a.row(), a.column())))
    app.tables_service.set_cell(table.id, table.rows[0].id, table.columns[0].id, item.id)
    assert [view.model.data(view.model.index(0, c)) for c in range(4)] == [
        "Меч",
        "1",
        "Острый",
        "0",
    ]
    app.tables_service.set_cell(table.id, table.rows[0].id, table.columns[1].id, "7")
    changes.clear()
    app.cards_service.update_card_fields(item.id, {"title": "Клинок", "summary": "", "cost": None})
    app.cards_service.update_section(
        item.id, item.description_id, content=text_document("<Опасный>")
    )
    assert {column for row, column in changes} == {0, 2, 3}
    assert embedded.model.data(embedded.model.index(0, 0)) == "Клинок"
    assert view.model.data(view.model.index(0, 2)) == "<Опасный>"
    assert view.model.data(view.model.index(0, 3)) == "—"
    app.cards_service.update_card(item.id, card_type="article")
    assert view.model.data(view.model.index(0, 0)) == "Предмет недоступен"
    replacement = app.create_card("Щит", card_type="item")
    app.tables_service.set_cell(table.id, table.rows[0].id, table.columns[0].id, replacement.id)
    assert view.model.data(view.model.index(0, 1)) == "7"
    app.actions.delete_entity(replacement.id)
    saved = app.tables_service.get_table(table.id)
    assert saved.rows[0].value(table.columns[0].id) == replacement.id
    assert view.model.data(view.model.index(0, 0)) == "Предмет недоступен"
    assert project.save_current()
    assert {key for key, value in project.store.load().tables[0].rows[0].cells} == {
        table.columns[0].id,
        table.columns[1].id,
    }
    backup = tmp_path / "refs.lodbackup"
    project.store.backup(backup)
    restored = SQLiteProjectStore.restore(backup, tmp_path / "restored")
    assert restored.load().tables == (saved,)
    restored.close()


def test_reference_constraints_atomic_tsv_and_missing_source(project, tmp_path, qtbot):
    app, project = project
    project.create_project(tmp_path / "world")
    _, _, table = inventory(app)
    view = app.tables.open_table(table.id).widget()
    model = view.model
    tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Warning)
    assert tester.model() is model
    other = app.create_card("Не предмет")
    before = app.tables_service.get_table(table.id)
    for invalid in (other.id, "Меч", "not-a-uuid"):
        with pytest.raises(ValueError):
            model.paste(model.index(0, 0), invalid + "\t5")
        assert app.tables_service.get_table(table.id) == before
    for invalid in ("0", "-2", "1.5", "", "nan"):
        assert not model.setData(model.index(0, 1), invalid)
        assert app.tables_service.get_table(table.id) == before
    item = app.create_card("Предмет", card_type="item")
    model.paste(model.index(0, 0), item.id + "\t5")
    before = app.tables_service.get_table(table.id)
    with pytest.raises(ValueError, match="read-only"):
        model.paste(model.index(0, 0), item.id + "\t5\tОписание")
    assert app.tables_service.get_table(table.id) == before
    assert not model.setData(model.index(0, 2), "Произвольный текст")
    new = before.new_row()
    app.tables_service.edit_table(table.id, rows=(*before.rows, new))
    app.tables_service.set_cell(table.id, new.id, table.columns[0].id, item.id)
    assert model.data(model.index(1, 1)) == "1"
    before = app.tables_service.get_table(table.id)
    app.tables_service.edit_table(
        table.id,
        columns=tuple(replace(c, position=i) for i, c in enumerate(before.columns[1:])),
        rows=tuple(
            replace(r, cells=tuple((k, v) for k, v in r.cells if k != table.columns[0].id))
            for r in before.rows
        ),
    )
    assert model.data(model.index(0, 1)) == "Источник проекции удалён"


def test_picker_alias_duplicate_titles_keyboard_and_selection(project, qtbot):
    app, _ = project
    _, _, table = inventory(app)
    first = app.create_card("Зелье", card_type="item")
    second = app.create_card("Зелье", card_type="item")
    app.cards_service.update_card_fields(second.id, {"aliases": ("Эликсир",)})
    app.create_card("Зелье", card_type="note")
    picker = EntityPicker(app.references, table.columns[0], current=second.id)
    qtbot.addWidget(picker)
    picker.show()
    assert picker.model.rowCount() == 2
    assert picker.list.currentIndex().data(Qt.ItemDataRole.UserRole) == second.id
    app.rename_card(first.id, "А")
    assert picker.list.currentIndex().data(Qt.ItemDataRole.UserRole) == second.id
    picker.query.setText("эликсир")
    assert picker.model.ids == (second.id,)
    qtbot.keyClick(picker.query, Qt.Key.Key_Return)
    assert picker.chosen_id == second.id
    cancelled = EntityPicker(app.references, table.columns[0])
    qtbot.addWidget(cancelled)
    cancelled.show()
    qtbot.keyClick(cancelled.query, Qt.Key.Key_Escape)
    assert cancelled.chosen_id is None and not cancelled.isVisible()


def test_generic_reference_projection_metadata_roundtrip(project, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    reference = ColumnDefinition("Событие", "entity_ref", ref_kind="card", ref_card_type="article")
    title = ColumnDefinition(
        "Заголовок", "projection", 1, source_column_id=reference.id, field_key="title"
    )
    table = app.tables_service.create_table("Обычная таблица", columns=(reference, title))
    app.tables_service.edit_table(table.id, rows=(table.new_row(),))
    event = app.create_card("Встреча", card_type="article")
    row = app.tables_service.get_table(table.id).rows[0]
    app.tables_service.set_cell(table.id, row.id, reference.id, event.id)
    assert project.save_current()
    assert project.store.load().tables == (app.tables_service.get_table(table.id),)


def test_generic_map_table_titles_live_and_map_undo_cannot_rename_entity(project):
    app, _ = project
    document = app.maps_service.create_map("Map", app.create_card("Asset ID").id)
    app.maps_service.add_layer(document.id, "Layer")
    app.actions.update_entity(document.id, title="Canonical title")
    app.maps_service.undo_stack(document.id).undo()
    assert app.maps_service.get_map(document.id).title == "Canonical title"
    assert app.references.info(document.id).value("title") == "Canonical title"
    table = app.tables_service.create_table("Table")
    app.tables_service.edit_table(table.id, title="Table renamed")
    assert app.references.info(table.id).value("title") == "Table renamed"


def test_tightening_reference_constraints_revalidates_existing_cells(project):
    app, _ = project
    column = ColumnDefinition("Документ", "entity_ref", ref_kind="card")
    table = app.tables_service.create_table("Table", columns=(column,))
    app.tables_service.edit_table(table.id, rows=(table.new_row(),))
    note = app.create_card("Note")
    app.tables_service.set_cell(
        table.id, app.tables_service.get_table(table.id).rows[0].id, column.id, note.id
    )
    before = app.tables_service.get_table(table.id)
    with pytest.raises(ValueError):
        app.tables_service.edit_table(table.id, columns=(replace(column, ref_card_type="item"),))
    assert app.tables_service.get_table(table.id) == before
