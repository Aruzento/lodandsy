import random
import sqlite3
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit

from lodandsy.application.module_controller import read_map_image
from lodandsy.application.module_session import ModuleSession
from lodandsy.application.sqlite_project_store import (
    ProjectError,
    ProjectSnapshot,
    SQLiteProjectStore,
    connect_database,
)
from lodandsy.domain.map_document import MapDocument, MapPin
from lodandsy.domain.tools import RandomTable, roll_dice

pytest_plugins = ["tests.project_fixture"]


def test_dice_details_total_and_repeatable_randomness():
    result = roll_dice(" 3d6 - 2 ", random.Random(4))
    assert result.dice == (2, 3, 1)
    assert result.total == 4 and result.modifier == -2
    assert "[2, 3, 1] -2 = 4" in result.text()
    assert len(roll_dice("d20").dice) == 1


@pytest.mark.parametrize("expression", ["", "0d6", "1d0", "1001d6", "1d1000001", "1d6+",
                                        "__import__('os')", "2d6*4", "2d6+1000000001", "9" * 81])
def test_dice_rejects_invalid_and_unbounded_input(expression):
    with pytest.raises(ValueError):
        roll_dice(expression)


def test_map_validation_undo_noops_and_immutable_state(qapp):
    session = ModuleSession()
    document = session.create_map("Map", str(uuid4()))
    pin = session.add_pin(document.id, "Point", .2, .3)
    session.edit_pin(document.id, pin.id, x=.7, card_id=str(uuid4()))
    session.undo_stack(document.id).undo()
    assert session.get_map(document.id).pins == (pin,)
    session.undo_stack(document.id).redo()
    assert session.get_map(document.id).pins[0].x == .7
    before = session.get_map(document.id)
    with pytest.raises(ValueError):
        session.edit_pin(document.id, pin.id, x=float("nan"))
    assert session.get_map(document.id) is before
    with pytest.raises(TypeError):
        session.maps[document.id] = document
    with pytest.raises(ValueError):
        MapPin("x", -1, 0)


def test_random_table_choice_and_empty_behavior():
    table = RandomTable("Table", rows=("", "First", " ", "Second"))
    assert table.choose(random.Random(1)) == (2, "First")
    with pytest.raises(ValueError):
        RandomTable("Empty").choose()


def test_real_map_table_card_workflow_and_project_roundtrip(project, tmp_path, qtbot):
    app, project = project
    project.create_project(tmp_path / "world")
    image_path = tmp_path / "карта.png"
    image = QImage(400, 200, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.darkGreen)
    assert image.save(str(image_path))
    app.modules.import_map(image_path, "World map")
    qtbot.waitUntil(lambda: not app.modules.importing)
    document = next(iter(app.modules.session.maps.values()))
    map_window = app.window_manager.find_window(f"map:{document.id}")
    first = app.create_card("First")
    second = app.create_card("Second")
    first_editor = app.open_card_editor(first.id).widget()
    second_editor = app.open_card_editor(second.id).widget()
    first_editor.text_edit.insertPlainText("First content")
    second_editor.text_edit.insertPlainText("Second content")
    one = app.modules.session.add_pin(document.id, "One", .1, .2, first.id)
    app.modules.session.add_pin(document.id, "Two", .8, .5, first.id)
    app.modules._pin_action(document.id, one.id, "open")
    assert app.open_card_editor(first.id).widget() is first_editor
    table = app.modules.session.create_table("Encounters")
    table_window = app.modules.open_table(table.id)
    widget = table_window.widget()
    widget.set_rows(("Goblin", "Dragon"))
    widget.rows_changed.emit(widget.rows())
    widget.roll_requested.click()
    widget.copy.click()
    assert QApplication.clipboard().text() == widget.result.text()
    dice = app.modules.open_dice().widget()
    dice.expression.setText("1d2+3")
    dice.roll.click()
    dice.copy.click()
    qtbot.waitUntil(lambda: QApplication.clipboard().text() == dice.result.toPlainText())
    assert len(app.window_manager.window_keys()) == 5
    assert project.save_current()
    revision = project.store.load().revision
    project._save_ui_state()
    app.delete_card(first.id)
    assert len(app.modules.session.get_map(document.id).pins) == 2
    assert "Разорванная" in map_window.widget().view._pins[0].toolTip()
    assert project.save_current()
    assert project.store.load().revision > revision
    before = project.store.load()
    root = project.store.root
    another = SQLiteProjectStore.create(tmp_path / "other")
    another.close()
    project.open_project(tmp_path / "other")
    assert not app.modules.session.maps and not app.modules.session.tables
    project.open_project(root)
    assert tuple(app.modules.session.maps.values()) == before.maps
    assert tuple(app.modules.session.tables.values()) == before.tables
    assert app.cards.get(second.id).content == "Second content"
    qtbot.waitUntil(lambda: "Колесо" in app.modules.open_map(document.id).widget().message.text())
    assert app.modules.open_map(document.id).widget().view.map_width == 400
    assert not project.saver.dirty


def test_live_table_editor_is_in_ctrl_s_snapshot(project, tmp_path, qtbot):
    app, project = project
    app.window.show()
    project.create_project(tmp_path / "world")
    table = app.modules.session.create_table("Table")
    app.modules.session.edit_table(table.id, rows=("Original",))
    widget = app.modules.open_table(table.id).widget()
    widget.table.editItem(widget.table.item(0, 0))
    editor = widget.table.findChild(QLineEdit)
    assert editor is not None
    editor.selectAll()
    qtbot.keyClicks(editor, "Live text")
    assert project.save_current()
    assert project.store.load().tables[0].rows == ("Live text",)


def test_random_table_result_preserves_literal_markup(project):
    app, project = project
    table = app.modules.session.create_table("Literal text")
    app.modules.session.edit_table(table.id, rows=("<b>Text</b>",))
    widget = app.modules.open_table(table.id).widget()
    widget.roll_requested.click()
    widget.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    widget.result.setSelection(0, len(widget.result.text()))
    assert widget.result.selectedText() == "1. <b>Text</b>"


def test_missing_map_image_remains_editable_and_keeps_links(project, tmp_path, qtbot):
    app, project = project
    project.create_project(tmp_path / "world")
    source = tmp_path / "image.png"
    image = QImage(10, 10, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.black)
    image.save(str(source))
    asset = project.store.import_asset(source)
    project.assets[asset.id] = asset
    document = app.modules.session.create_map("Map", asset.id)
    app.modules.session.add_pin(document.id, "Broken", .5, .5, str(uuid4()))
    (project.store.root / asset.path).unlink()
    widget = app.modules.open_map(document.id).widget()
    qtbot.waitUntil(lambda: "недоступно" in widget.message.text())
    assert len(widget.view._pins) == 1
    assert "Разорванная" in widget.view._pins[0].toolTip()


def test_map_image_policy_rejects_svg_and_oversize_header(tmp_path):
    svg = tmp_path / "image.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>')
    with pytest.raises(ValueError, match="Поддерживаются"):
        read_map_image(svg)


def test_marker_commands_link_new_card_rename_move_unlink_and_undo(project, tmp_path, monkeypatch):
    app, project = project
    session = app.modules.session
    document = session.create_map("Map", str(uuid4()))
    pin = session.add_pin(document.id, "Point", .2, .3)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("New Card", True))
    app.modules._pin_action(document.id, pin.id, "create")
    card = app.cards.all()[0]
    assert session.get_map(document.id).pins[0].card_id == card.id
    app.modules._pin_action(document.id, pin.id, "rename")
    assert session.get_map(document.id).pins[0].title == "New Card"
    app.modules._pin_action(document.id, pin.id, "unlink")
    assert session.get_map(document.id).pins[0].card_id is None
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: (a[3][0], True))
    app.modules._pin_action(document.id, pin.id, "link")
    assert session.get_map(document.id).pins[0].card_id == card.id
    other = session.create_map("Other", document.asset_id)
    session.add_pin(other.id, "Second placement", .7, .8, card.id)
    session.edit_pin(document.id, pin.id, x=.6, y=.5)
    session.undo_stack(document.id).undo()
    assert session.get_map(document.id).pins[0].x == .2
    app.modules._pin_action(document.id, pin.id, "delete")
    assert not session.get_map(document.id).pins
    session.undo_stack(document.id).undo()
    assert session.get_map(document.id).pins[0].card_id == card.id
    assert session.get_map(other.id).pins[0].card_id == card.id


def test_failed_image_import_does_not_publish_map_or_asset(project, tmp_path, qtbot, monkeypatch):
    app, project = project
    project.create_project(tmp_path / "world")
    bad = tmp_path / "not-image.png"
    bad.write_bytes(b"not an image")
    errors = []
    monkeypatch.setattr(app.modules, "_error", errors.append)
    app.modules.import_map(bad, "Rejected")
    qtbot.waitUntil(lambda: not app.modules.importing)
    assert errors and not app.modules.session.maps and not project.assets
    assert not project.saver.dirty


def test_v2_module_migration_and_transaction_rollback(tmp_path, monkeypatch):
    store = SQLiteProjectStore.create(tmp_path / "world")
    with closing(connect_database(store.path)) as connection, connection:
        connection.execute("DROP TABLE map_document")
        connection.execute("DROP TABLE random_table")
        connection.execute("PRAGMA user_version=2")
    store.close()
    original = SQLiteProjectStore._upgrade_v2
    def fail(connection):
        original(connection)
        raise sqlite3.OperationalError("interrupted")
    monkeypatch.setattr(SQLiteProjectStore, "_upgrade_v2", staticmethod(fail))
    with pytest.raises(ProjectError, match="original schema retained"):
        SQLiteProjectStore.open(store.root)
    with closing(connect_database(store.path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (2,)
        assert not connection.execute(
            "SELECT name FROM sqlite_master WHERE name='map_document'"
        ).fetchall()
    monkeypatch.setattr(SQLiteProjectStore, "_upgrade_v2", staticmethod(original))
    reopened = SQLiteProjectStore.open(store.root)
    assert reopened.load().maps == ()
    reopened.close()


def test_all_modules_backup_restore_and_future_payload_is_preserved(tmp_path):
    source = tmp_path / "image.bin"
    source.write_bytes(b"image bytes")
    store = SQLiteProjectStore.create(tmp_path / "world")
    asset = store.import_asset(source)
    document = MapDocument("Map", asset.id, pins=(MapPin("Gone", .1, .2, card_id=str(uuid4())),))
    table = RandomTable("Table", rows=("One", "Two"))
    snapshot = ProjectSnapshot((), 1, (asset,), (document,), (table,))
    store.save(snapshot)
    backup = tmp_path / "world.lodbackup"
    store.backup(backup)
    restored = SQLiteProjectStore.restore(backup, tmp_path / "restored")
    assert restored.load() == snapshot
    restored.close()
    with closing(connect_database(store.path)) as connection, connection:
        connection.execute("UPDATE map_document SET payload_version=999")
    with pytest.raises(ProjectError, match="Unsupported Map"):
        store.save(replace(snapshot, revision=2))
    with closing(connect_database(store.path)) as connection:
        assert connection.execute("SELECT payload_version FROM map_document").fetchone() == (999,)
        assert connection.execute("SELECT revision FROM metadata").fetchone() == (1,)
    store.close()
