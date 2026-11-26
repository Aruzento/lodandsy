from dataclasses import replace

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QAbstractItemModelTester
from PySide6.QtWidgets import QApplication, QLineEdit

from lodandsy.application.save_coordinator import SaveState
from lodandsy.domain.table_document import ColumnDefinition, RowRecord

pytest_plugins = ["tests.project_fixture"]


def type_unicode(widget, text):
    # Real key events; QTest.keyClicks itself only accepts Latin-1 on this Qt build.
    for character in text:
        QApplication.sendEvent(
            widget, QKeyEvent(QEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, character)
        )
        QApplication.sendEvent(
            widget, QKeyEvent(QEvent.Type.KeyRelease, 0, Qt.KeyboardModifier.NoModifier, character)
        )


def table_views(app):
    table = app.tables_service.create_table("Таблица")
    number = ColumnDefinition("Число", "number", 1)
    table = app.tables_service.edit_table(
        table.id, columns=(*table.columns, number), rows=(RowRecord(), RowRecord(1))
    )
    first, second = app.tables.table_view(table.id), app.tables.table_view(table.id)
    return table, first, second


def active_editor(view, qtbot, row=0, column=0):
    view.show()
    view.activateWindow()
    view.table.setCurrentIndex(view.model.index(row, column))
    view.table.edit(view.model.index(row, column))
    qtbot.waitUntil(lambda: any(e.isVisible() for e in view.table.findChildren(QLineEdit)))
    control = next(e for e in view.table.findChildren(QLineEdit) if e.isVisible())
    control.setFocus()
    qtbot.waitUntil(control.hasFocus)
    return control


def test_table_typing_two_views_pause_cursor_selection_undo_commit_and_escape(project, qtbot):
    app, _ = project
    table, first, second = table_views(app)
    qtbot.addWidget(first)
    qtbot.addWidget(second)
    tester = QAbstractItemModelTester(
        first.model, QAbstractItemModelTester.FailureReportingMode.Warning
    )
    assert tester.model() is first.model
    editor = active_editor(first, qtbot)
    qtbot.keyClicks(editor, "Dragon")
    qtbot.wait(810)  # Explicit regression scenario: the previous debounce stole focus at 750ms.
    assert editor.hasFocus() and editor.text() == "Dragon"
    assert second.model.data(second.model.index(0, 0)) == ""
    editor.setCursorPosition(3)
    type_unicode(editor, "Ж")
    qtbot.keyClick(editor, Qt.Key.Key_Backspace)
    qtbot.keyClicks(editor, "-tail")
    editor.setSelection(0, 3)
    app.tables_service.set_cell(table.id, table.rows[1].id, table.columns[1].id, "12")
    assert editor.hasFocus() and editor.selectedText() == "Dra"
    qtbot.keyClick(editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert editor.text() == "Dragon"
    editor.selectAll()
    type_unicode(editor, "Дракон")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.waitUntil(
        lambda: (
            app.tables_service.get_table(table.id).rows[0].value(table.columns[0].id) == "Дракон"
        )
    )
    assert second.model.data(second.model.index(0, 0)) == "Дракон"
    editor = active_editor(first, qtbot)
    editor.selectAll()
    qtbot.keyClicks(editor, "Cancelled")
    qtbot.keyClick(editor, Qt.Key.Key_Escape)
    assert app.tables_service.get_table(table.id).rows[0].value(table.columns[0].id) == "Дракон"
    assert not app.tables_service.draft_count


def test_save_flush_keeps_active_editor_and_io_failure_retry(project, qtbot, tmp_path, monkeypatch):
    app, project = project
    project.create_project(tmp_path / "world")
    table, first, second = table_views(app)
    qtbot.addWidget(first)
    qtbot.addWidget(second)
    editor = active_editor(first, qtbot)
    qtbot.keyClicks(editor, "First")
    editor.setCursorPosition(2)
    assert app.tables_service.pending_count == 1 and project.saver.dirty
    assert project.save_current()
    assert editor.hasFocus() and editor.cursorPosition() == 2 and editor.isUndoAvailable()
    assert project.store.load().tables[0].rows[0].value(table.columns[0].id) == "First"
    qtbot.keyClicks(editor, "Next")
    save = project.saver._persist
    monkeypatch.setattr(
        project.saver, "_persist", lambda snapshot: (_ for _ in ()).throw(OSError("disk"))
    )
    assert not project.save_current() and project.saver.state == SaveState.ERROR
    assert editor.hasFocus() and editor.text() == "FiNextrst"
    monkeypatch.setattr(project.saver, "_persist", save)
    assert project.save_current()
    assert second.model.data(second.model.index(0, 0)) == "FiNextrst"
    assert project.store.load().tables[0].rows[0].value(table.columns[0].id) == "FiNextrst"


def test_concurrent_cell_conflict_reorder_and_deleted_row_keep_raw_draft(project, qtbot):
    app, _ = project
    table, first, second = table_views(app)
    qtbot.addWidget(first)
    qtbot.addWidget(second)
    editor = active_editor(first, qtbot)
    qtbot.keyClicks(editor, "Mine")
    app.tables_service.set_cell(table.id, table.rows[0].id, table.columns[0].id, "Other")
    assert editor.text() == "Mine" and editor.hasFocus()
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: bool(app.tables_service.drafts(table.id)))
    assert app.tables_service.get_table(table.id).rows[0].value(table.columns[0].id) == "Other"
    assert app.tables_service.drafts(table.id)[(table.rows[0].id, table.columns[0].id)] == "Mine"
    app.tables.discard_drafts(table.id)
    editor = active_editor(first, qtbot)
    editor.selectAll()
    qtbot.keyClicks(editor, "Moved")
    current = app.tables_service.get_table(table.id)
    app.tables_service.edit_table(
        table.id,
        rows=tuple(replace(row, position=i) for i, row in enumerate(reversed(current.rows))),
    )
    assert editor.text() == "Moved" and editor.hasFocus()
    qtbot.keyClick(editor, Qt.Key.Key_Tab)
    qtbot.waitUntil(
        lambda: app.tables_service.get_table(table.id).rows[1].value(table.columns[0].id) == "Moved"
    )
    editor = active_editor(first, qtbot, row=1)
    editor.selectAll()
    qtbot.keyClicks(editor, "Deleted row raw")
    current = app.tables_service.get_table(table.id)
    app.tables_service.edit_table(table.id, rows=(current.rows[0],))
    qtbot.waitUntil(lambda: bool(app.tables_service.orphan_drafts))
    assert app.tables_service.orphan_drafts[0][1] == "Deleted row raw"


def test_header_and_inspector_typing_do_not_publish_per_character(project, qtbot, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    app.window.show()
    app.window.activateWindow()
    card = app.create_card("Original", card_type="character")
    view = app.open_card_editor(card.id).widget()
    title = view.title_edit
    title.setFocus()
    qtbot.waitUntil(title.hasFocus)
    title.selectAll()
    qtbot.keyClicks(title, "New title")
    assert app.cards.get(card.id).title == "Original" and title.hasFocus()
    qtbot.wait(810)
    assert title.text() == "New title" and title.hasFocus()
    title.setSelection(0, 3)
    app.cards_service.update_card_fields(card.id, {"hp_max": 42})
    assert title.selectedText() == "New"
    qtbot.keyClick(title, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: app.cards.get(card.id).title == "New title")
    assert title.hasFocus() and title.selectedText() == "New" and title.isUndoAvailable()
    app.card_views.open_game_sheet(card.id)
    hp = view.game_sheet.controls["hp_max"]
    hp.setFocus()
    qtbot.waitUntil(hp.hasFocus)
    hp.selectAll()
    qtbot.keyClicks(hp, "100")
    assert hp.text() == "100" and app.cards.get(card.id).value("hp_max") == 42
    qtbot.keyClick(hp, Qt.Key.Key_Return)
    assert app.cards.get(card.id).value("hp_max") == 100
    hp.selectAll()
    qtbot.keyClicks(hp, "nan")
    qtbot.keyClick(hp, Qt.Key.Key_Return)
    assert app.cards.get(card.id).value("hp_max") == 100 and project.draft_count == 1
    assert project.save_current()
    assert project.store.load().cards[0].value("hp_max") == 100
