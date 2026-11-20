from lodandsy.application.cards_service import CardsService
from lodandsy.application.tables_service import TablesService

pytest_plugins = ["tests.project_fixture"]


def test_reopening_field_conflict_cannot_silently_overwrite(qapp):
    cards = CardsService()
    card = cards.create_card("Original")
    edits = cards.field_edits
    key = (card.id, "title")
    a, b = edits.begin(key), edits.begin(key)
    edits.text(a, "A")
    edits.text(b, "B")
    assert edits.commit(b, finish=True)
    assert not edits.commit(a, finish=True)
    reopened = edits.begin(key)
    edits.commit(reopened, finish=True)
    assert cards.cards.get(card.id).title == "B"
    edits.flush()
    assert cards.cards.get(card.id).title == "B"
    cards.update_card_fields(card.id, {"title": "C"})
    assert not edits.resolve(key, mine=True)
    assert cards.cards.get(card.id).title == "C"
    assert edits.resolve(key, mine=True)
    assert cards.cards.get(card.id).title == "A"
    assert not edits.conflicts and not edits.drafts


def test_reopening_cell_conflict_cannot_silently_overwrite(qapp):
    tables = TablesService()
    table = tables.create_table("Table")
    from dataclasses import replace

    from lodandsy.domain.table_document import RowRecord

    row = replace(table, rows=(RowRecord(0),))
    tables.update_table(row)
    key = table.id, row.rows[0].id, row.columns[0].id
    a, b = tables.begin_edit(*key), tables.begin_edit(*key)
    tables.edit_text(a, "A")
    tables.edit_text(b, "B")
    assert tables.commit_edit(b, finish=True)
    assert not tables.commit_edit(a, finish=True)
    reopened = tables.begin_edit(*key)
    tables.commit_edit(reopened, finish=True)
    assert tables.get_table(table.id).rows[0].value(key[2]) == "B"
    tables.set_cell(*key, "C")
    assert not tables.resolve_conflict(*key, mine=True)
    assert tables.get_table(table.id).rows[0].value(key[2]) == "C"
    assert tables.resolve_conflict(*key, mine=True)
    assert tables.get_table(table.id).rows[0].value(key[2]) == "A"
    assert not tables.conflicts and not tables.drafts(table.id)


def test_field_use_saved_invalid_draft_and_existing_owner_cannot_reapply(qapp):
    cards = CardsService()
    card = cards.create_card("Original")
    edits = cards.field_edits
    key = (card.id, "title")
    a = edits.begin(key)
    edits.text(a, "")
    assert not edits.commit(a, finish=True)
    cards.update_card_fields(card.id, {"title": "B"})
    a = edits.begin(key)
    edits.text(a, "A")
    assert not edits.commit(a)
    assert edits.resolve(key)
    edits.commit(a)
    assert cards.cards.get(card.id).title == "B" and not edits.drafts


def test_real_card_editor_conflict_controls_and_ctrl_s(project, tmp_path, qtbot):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Original")
    editor = app.open_card_editor(card.id).widget()
    edits = app.cards_service.field_edits
    key = (card.id, "title")
    a = edits.begin(key)
    edits.text(a, "A")
    app.cards_service.update_card_fields(card.id, {"title": "B"})
    assert not edits.commit(a, finish=True)
    assert editor.conflicts.fields.count() == 1
    assert project.save_current()
    assert project.store.load().cards[0].title == "B"
    editor.conflicts.resolve_requested.emit(key, False)
    assert editor.title_edit.text() == "B"
    assert not edits.conflicts


def test_embedded_standalone_conflict_resolution_preserves_both_models(project, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Owner", card_type="character")
    section = next(s for s in card.sections if s.purpose == "inventory")
    table = app.actions.section_table(card.id, section.id)
    editor = app.open_card_editor(card.id).widget()
    editor.select_section(section.id)
    embedded = editor._embedded_tables[section.id]
    standalone = app.tables.open_table(table.id).widget()
    standalone.add_row()
    for first, other in ((embedded, standalone), (standalone, embedded)):
        a, _ = first.model.begin_editor(first.model.index(0, 1))
        b, _ = other.model.begin_editor(other.model.index(0, 1))
        first.model.edit_text(a, "7")
        other.model.edit_text(b, "8")
        assert other.model.commit_editor(b)
        assert not first.model.commit_editor(a)
        reopened, raw = first.model.begin_editor(first.model.index(0, 1))
        assert raw == "7"
        assert not first.model.commit_editor(reopened)
        assert project.save_current()
        assert first.model.document.rows[0].value(table.columns[1].id) == 8
        key = (table.id, first.model.document.rows[0].id, table.columns[1].id)
        assert first.conflicts.fields.count() == 1 and other.conflicts.fields.count() == 1
        first.conflicts.resolve_requested.emit(key, False)
        assert not app.tables_service.conflicts
        assert other.model.data(other.model.index(0, 1)) == "8"
        app.tables_service.set_cell(*key, "1")


def test_card_metadata_update_keeps_embedded_native_input(project, qtbot):
    from PySide6.QtWidgets import QApplication, QLineEdit

    app, _ = project
    app.window.show()
    card = app.create_card("Owner", card_type="character")
    section = next(s for s in card.sections if s.purpose == "inventory")
    table = app.actions.section_table(card.id, section.id)
    editor = app.open_card_editor(card.id).widget()
    editor.select_section(section.id)
    embedded = editor._embedded_tables[section.id]
    embedded.add_row()
    QApplication.processEvents()
    embedded.table.edit(embedded.model.index(0, 1))
    control = next(e for e in embedded.table.findChildren(QLineEdit) if e.isVisible())
    control.selectAll()
    qtbot.keyClicks(control, "77")
    app.cards_service.update_card_fields(card.id, {"summary": "Updated elsewhere"})
    QApplication.processEvents()
    assert control.isVisible() and control.text() == "77"
    assert app.tables_service.get_table(table.id).rows[0].value(table.columns[1].id) == 1


def test_picker_expected_conflict_keeps_draft_after_reopening(project):
    from dataclasses import replace

    from lodandsy.domain.table_document import ColumnDefinition, RowRecord

    app, _ = project
    cards = [app.create_card(title) for title in ("A", "B", "C")]
    table = app.tables_service.create_table("References")
    column = ColumnDefinition("Card", "entity_ref", ref_kind="card")
    row = RowRecord(0, ((column.id, cards[0].id),))
    app.tables_service.update_table(replace(table, columns=(column,), rows=(row,)))
    key = table.id, row.id, column.id
    app.tables_service.set_cell(*key, cards[1].id)
    try:
        app.tables_service.set_cell(*key, cards[2].id, expected=cards[0].id, parsed=True)
    except ValueError as error:
        app.tables_service.reject_draft(*key, cards[2].id, error)
    owner = app.tables_service.begin_edit(*key)
    assert not app.tables_service.commit_edit(owner, finish=True)
    assert app.tables_service.get_table(table.id).rows[0].value(column.id) == cards[1].id
