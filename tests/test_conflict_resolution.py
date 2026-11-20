from dataclasses import replace
from types import SimpleNamespace

import pytest

from lodandsy.application.cards_service import CardsService
from lodandsy.application.tables_service import TablesService
from lodandsy.domain.table_document import ColumnDefinition, RowRecord

pytest_plugins = ["tests.project_fixture"]


@pytest.fixture(params=["field", "cell"])
def buffer(request, qapp):
    return make_buffer(request.param)


def make_buffer(kind, *, numeric=False):
    if kind == "field":
        cards = CardsService()
        card = cards.create_card("Original", card_type="character")
        field = "hp" if numeric else "title"
        edits, key = cards.field_edits, (card.id, field)
        return SimpleNamespace(
            begin=lambda: edits.begin(key),
            text=edits.text,
            commit=edits.commit,
            cancel=edits.cancel,
            flush=edits.flush,
            read=lambda: cards.get_card(card.id).value(field),
            write=lambda raw: cards.update_card_fields(card.id, {field: raw}),
            draft=lambda: edits.drafts.get(key),
            conflict=lambda: edits.conflicts.get(key),
            error=lambda: edits.errors.get(key),
            resolve=lambda mine: edits.resolve(key, mine=mine),
        )
    tables = TablesService()
    table = tables.create_table(
        "Table", columns=(ColumnDefinition("Number", "number"),) if numeric else None
    )
    row = RowRecord(0)
    tables.update_table(replace(table, rows=(row,)))
    key = table.id, row.id, table.columns[0].id
    if not numeric:
        tables.set_cell(*key, "Original")
    return SimpleNamespace(
        begin=lambda: tables.begin_edit(*key),
        text=tables.edit_text,
        commit=tables.commit_edit,
        cancel=tables.cancel_edit,
        flush=tables.flush_edits,
        read=lambda: tables.get_table(table.id).rows[0].value(key[2]),
        write=lambda raw: tables.set_cell(*key, raw),
        draft=lambda: tables.drafts(table.id).get(key[1:]),
        conflict=lambda: tables.conflicts.get(key),
        error=lambda: tables.draft_error(*key),
        resolve=lambda mine: tables.resolve_conflict(*key, mine=mine),
    )


@pytest.mark.parametrize("finish", [False, True])
@pytest.mark.parametrize("mine", [False, True])
def test_cancel_flushed_winner_keeps_other_owners_conflict(buffer, finish, mine):
    a, b = buffer.begin(), buffer.begin()
    buffer.text(a, "A")
    buffer.text(b, "B")
    assert buffer.commit(b, finish=False)
    assert not buffer.commit(a, finish=finish)
    buffer.flush()
    conflict, error = replace(buffer.conflict()), buffer.error()
    buffer.cancel(b)
    assert buffer.read() == "B"
    assert buffer.draft() == "A"
    assert buffer.conflict() == conflict and buffer.error() == error
    reopened = buffer.begin()
    assert not buffer.commit(reopened, finish=True)
    assert buffer.resolve(mine)
    assert buffer.read() == ("A" if mine else "B")
    buffer.cancel(a)
    assert buffer.draft() is None and buffer.conflict() is None


def test_cancel_old_owner_cannot_restore_older_draft(buffer):
    a, b = buffer.begin(), buffer.begin()
    buffer.text(a, "A")
    buffer.text(b, "B")
    assert buffer.commit(b, finish=True)
    assert not buffer.commit(a, finish=True)
    old, newer = buffer.begin(), buffer.begin()
    buffer.text(newer, "New draft")
    assert not buffer.commit(newer, finish=True)
    conflict, error = replace(buffer.conflict()), buffer.error()
    buffer.cancel(old)
    assert buffer.draft() == "New draft"
    assert buffer.conflict() == conflict and buffer.error() == error
    assert buffer.read() == "B"


def test_cancel_old_owner_cannot_undo_new_conflict_observation(buffer):
    a = buffer.begin()
    buffer.text(a, "A")
    buffer.write("B")
    assert not buffer.commit(a, finish=True)
    old = buffer.begin()
    buffer.write("C")
    assert not buffer.resolve(True)
    conflict, error = replace(buffer.conflict()), buffer.error()
    buffer.cancel(old)
    assert buffer.conflict() == conflict and buffer.error() == error
    assert buffer.draft() == "A" and buffer.read() == "C"
    assert buffer.resolve(True) and buffer.read() == "A"


def test_cancel_own_conflict_edit_restores_original_status(buffer):
    a = buffer.begin()
    buffer.text(a, "A")
    buffer.write("B")
    assert not buffer.commit(a, finish=True)
    conflict, error = replace(buffer.conflict()), buffer.error()
    owner = buffer.begin()
    buffer.text(owner, "Changed draft")
    assert not buffer.commit(owner)
    buffer.cancel(owner)
    assert buffer.draft() == "A" and buffer.read() == "B"
    assert buffer.conflict() == conflict and buffer.error() == error


@pytest.mark.parametrize("kind", ["field", "cell"])
def test_cancel_invalid_numeric_draft_preserves_none_baseline(kind, qapp):
    buffer = make_buffer(kind, numeric=True)
    assert buffer.read() is None
    a = buffer.begin()
    buffer.text(a, "invalid")
    assert not buffer.commit(a, finish=True)
    owner = buffer.begin()
    buffer.text(owner, "nan")
    assert not buffer.commit(owner)
    buffer.cancel(owner)
    assert buffer.draft() == "invalid"
    buffer.write(8)
    reopened = buffer.begin()
    buffer.text(reopened, "7")
    assert not buffer.commit(reopened, finish=True)
    assert buffer.read() == 8 and buffer.conflict() is not None


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


def test_native_field_escape_after_save_preserves_other_editor_conflict(project, qtbot, tmp_path):
    from PySide6.QtCore import Qt

    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Original")
    editor = app.open_card_editor(card.id).widget()
    app.window.show()
    with qtbot.waitActive(app.window):
        app.window.activateWindow()
    edits, key = app.cards_service.field_edits, (card.id, "title")
    other = edits.begin(key)
    control = editor.title_edit
    control.setFocus()
    qtbot.waitUntil(control.hasFocus)
    control.selectAll()
    qtbot.keyClicks(control, "B")
    qtbot.keyClick(control, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: app.cards.get(card.id).title == "B")
    edits.text(other, "A")
    assert not edits.commit(other, finish=True)
    qtbot.keyClick(control, Qt.Key.Key_Escape)
    assert edits.drafts[key] == "A" and key in edits.conflicts
    editor.text_edit.setFocus()  # Blur after Escape must not make the draft authoritative.
    qtbot.waitUntil(editor.text_edit.hasFocus)
    assert project.save_current()
    assert project.store.load().cards[0].title == "B"
    assert edits.drafts[key] == "A" and editor.conflicts.fields.count() == 1
    editor.conflicts.resolve_requested.emit(key, True)
    assert app.cards.get(card.id).title == "A" and key not in edits.conflicts


@pytest.mark.parametrize("winner_embedded", [False, True])
def test_native_table_escape_after_flush_preserves_other_view_conflict(
    project, qtbot, tmp_path, winner_embedded
):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLineEdit

    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Owner", card_type="character")
    section = next(s for s in card.sections if s.purpose == "inventory")
    table = app.actions.section_table(card.id, section.id)
    editor = app.open_card_editor(card.id).widget()
    editor.select_section(section.id)
    embedded = editor._embedded_tables[section.id]
    standalone = app.tables.open_table(table.id).widget()
    embedded.add_row()
    winner, other = (embedded, standalone) if winner_embedded else (standalone, embedded)
    # Two independent model owners are open before the native winner performs Ctrl+S.
    a, _ = other.model.begin_editor(other.model.index(0, 1))
    app.window.show()
    app.window_manager.focus_window(
        f"card-editor:{card.id}" if winner_embedded else f"table:{table.id}"
    )
    with qtbot.waitActive(app.window):
        app.window.activateWindow()
    index = winner.model.index(0, 1)
    winner.table.setCurrentIndex(index)
    winner.table.edit(index)
    qtbot.waitUntil(lambda: any(e.isVisible() for e in winner.table.findChildren(QLineEdit)))
    control = next(e for e in winner.table.findChildren(QLineEdit) if e.isVisible())
    control.setFocus()
    qtbot.waitUntil(control.hasFocus)
    control.selectAll()
    qtbot.keyClicks(control, "8")
    qtbot.keyClick(control, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    key = table.id, winner.model.document.rows[0].id, table.columns[1].id
    qtbot.waitUntil(lambda: app.tables_service.get_table(table.id).rows[0].value(key[2]) == 8)
    other.model.edit_text(a, "7")
    assert not other.model.commit_editor(a)
    qtbot.keyClick(control, Qt.Key.Key_Escape)
    winner.table.setFocus()
    qtbot.waitUntil(winner.table.hasFocus)
    assert app.tables_service.drafts(table.id)[key[1:]] == "7"
    assert key in app.tables_service.conflicts
    assert project.save_current()
    assert project.store.load().tables[0].rows[0].value(key[2]) == 8
    other.conflicts.resolve_requested.emit(key, False)
    assert key not in app.tables_service.conflicts
    assert winner.model.data(winner.model.index(0, 1)) == "8"
