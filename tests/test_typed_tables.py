import random
from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox

from lodandsy.application.sqlite_project_store import ProjectSnapshot, SQLiteProjectStore
from lodandsy.domain.table_document import ColumnDefinition, RandomTable, RowRecord
from lodandsy.ui.table_widget import RandomTableWidget

pytest_plugins = ["tests.project_fixture"]


def typed_table(title="Table"):
    columns = tuple(
        ColumnDefinition(name, kind, i)
        for i, (name, kind) in enumerate(
            [("Событие", "text"), ("Количество", "number"), ("Есть", "bool")]
        )
    )
    table = RandomTable(title, columns=columns, rows=(RowRecord(0), RowRecord(1)))
    table = table.with_cell(table.rows[1].id, columns[0].id, "<b>Dragon</b>")
    table = table.with_cell(table.rows[1].id, columns[1].id, 0)
    return table.with_cell(table.rows[1].id, columns[2].id, False)


def test_types_ids_order_random_whole_row_and_rejections():
    table = typed_table()
    index, row = table.choose(random.Random(3))
    assert index == 2 and row == table.rows[1]
    assert "Количество: 0" in table.row_text(row) and "Есть: false" in table.row_text(row)
    for col, bad in [(0, 12), (1, True), (1, float("nan")), (2, "false")]:
        with pytest.raises(ValueError):
            table.with_cell(row.id, table.columns[col].id, bad)
    with pytest.raises(ValueError, match="Duplicate"):
        replace(table, columns=(table.columns[0], table.columns[0]))
    with pytest.raises(ValueError, match="order"):
        replace(table, rows=(replace(row, position=2),))
    zero = replace(table, rows=(RowRecord(0, ((table.columns[1].id, 0),)),))
    assert zero.choose()[0] == 1
    false = replace(table, rows=(RowRecord(0, ((table.columns[2].id, False),)),))
    assert false.choose()[0] == 1


def test_model_tsv_atomic_checkbox_and_copy(qtbot):
    table = typed_table()
    widget = RandomTableWidget(table)
    qtbot.addWidget(widget)
    model = widget.model
    model.paste(model.index(0, 0), "Wolf\t2\ttrue")
    assert model.document.rows[0].value(table.columns[1].id) == 2
    before = model.document
    with pytest.raises(ValueError):
        model.paste(model.index(0, 0), "Changed\tbad\ttrue")
    assert model.document == before
    assert not model.setData(model.index(0, 1), "bad")
    model.paste(model.index(0, 0), "Wolf\t2\ttrue")
    assert not model.drafts
    before = model.document
    for bad in ('"unclosed', "X" * 200000, "\n" * 100000):
        with pytest.raises(ValueError):
            model.paste(model.index(0, 0), bad)
        assert model.document == before
    assert model.setData(
        model.index(0, 2), Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole
    )
    assert model.document.rows[0].value(table.columns[2].id) is False
    widget.table.selectRow(0)
    widget.copy_selection()
    assert QApplication.clipboard().text() == "Wolf\t2\tfalse"


def test_column_row_commands_reorder_rename_delete_cancel_and_type_rejection(qtbot, monkeypatch):
    table = typed_table()
    widget = RandomTableWidget(table)
    qtbot.addWidget(widget)
    widget.table.setCurrentIndex(widget.model.index(1, 0))
    widget.move_row(-1)
    assert widget.model.document.rows[0].id == table.rows[1].id
    widget.table.setCurrentIndex(widget.model.index(0, 0))
    widget.move_column(1)
    assert widget.model.document.columns[1].id == table.columns[0].id
    assert widget.model.document.rows[0].value(table.columns[0].id) == "<b>Dragon</b>"
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No)
    before = widget.model.document
    widget.remove_row()
    assert widget.model.document == before
    widget.table.setCurrentIndex(widget.model.index(0, 1))
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Renamed", True))
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("number", True))
    widget.edit_column()
    assert widget.model.document == before and widget.error.text()
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("text", True))
    widget.edit_column()
    assert widget.model.document.columns[1].name == "Renamed"
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    widget.remove_column()
    assert all(k != table.columns[0].id for r in widget.model.document.rows for k, _ in r.cells)
    widget.add_column()
    assert widget.model.document.columns[-1].name == "Renamed"


def test_live_invalid_draft_survives_close_blocks_save_and_can_be_fixed(project, qtbot, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    table = app.modules.session.create_table("Table")
    source = typed_table()
    app.modules.session.edit_table(table.id, columns=source.columns, rows=source.rows)
    widget = app.modules.open_table(table.id).widget()
    assert not widget.model.setData(widget.model.index(0, 1), "bad")
    assert not project.save_current()
    app.window_manager.close_window(f"table:{table.id}")
    widget = app.modules.open_table(table.id).widget()
    assert widget.model.data(widget.model.index(0, 1)) == "bad"
    assert widget.model.setData(widget.model.index(0, 1), "0")
    assert project.save_current()
    assert project.store.load().tables[0].rows[0].value(source.columns[1].id) == 0
    widget.show()
    widget.table.edit(widget.model.index(0, 0))
    editor = widget.table.findChild(QLineEdit)
    assert editor is not None
    qtbot.keyClicks(editor, "Live")
    assert project.save_current()
    assert project.store.load().tables[0].rows[0].value(source.columns[0].id) == "Live"


def test_normalized_storage_backup_ids_and_cell_fk(tmp_path):
    import sqlite3
    from contextlib import closing

    from lodandsy.application.sqlite_project_store import connect_database

    table = typed_table()
    store = SQLiteProjectStore.create(tmp_path / "world")
    snapshot = ProjectSnapshot((), 1, tables=(table,))
    store.save(snapshot)
    assert store.load() == snapshot
    with closing(connect_database(store.path)) as connection, connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO table_cell VALUES(?,?,?,?)",
                (table.id, table.rows[0].id, table.rows[1].id, "0"),
            )
    archive = tmp_path / "backup.zip"
    store.backup(archive)
    restored = SQLiteProjectStore.restore(archive, tmp_path / "restored")
    assert restored.load().tables == (table,)
    restored.close()
    store.close()
