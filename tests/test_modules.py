import random
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit

from lodandsy.application.map_pyramid import ensure_pyramid
from lodandsy.application.rich_html import html_text
from lodandsy.application.sqlite_project_store import (
    ProjectError,
    ProjectSnapshot,
    SQLiteProjectStore,
    connect_database,
)
from lodandsy.domain.card import Card
from lodandsy.domain.dice import roll_dice
from lodandsy.domain.map_document import MapDocument, TokenInstance
from tests.project_fixture import map_services, record_rows, text_table, text_values

pytest_plugins = ["tests.project_fixture"]


def test_dice_details_total_and_repeatable_randomness():
    from lodandsy.domain.dice import DiceConfig

    result = roll_dice(DiceConfig((0, 3, 0, 0, 0, 0, 0), -2), random.Random(4))
    assert result.groups == ((6, (2, 3, 1)),)
    assert result.total == 4 and result.modifier == -2
    assert "Итог = 4" in result.text()


def test_map_validation_undo_noops_and_immutable_state(qapp):
    session, actions, tables, cards_service = map_services()
    document = session.create_map("Map", str(uuid4()))
    pin = actions.add_card_placement(Card("Point"), document.id, 0.2, 0.3)
    session.edit_token(document.id, pin.id, x=0.7, label_override="Local")
    session.undo_stack(document.id).undo()
    assert session.get_map(document.id).tokens == (pin,)
    session.undo_stack(document.id).redo()
    assert session.get_map(document.id).tokens[0].x == 0.7
    before = session.get_map(document.id)
    with pytest.raises(ValueError):
        session.edit_token(document.id, pin.id, x=float("nan"))
    assert session.get_map(document.id) is before
    with pytest.raises(TypeError):
        session.maps[document.id] = document
    with pytest.raises(ValueError):
        TokenInstance(str(uuid4()), -1, 0)


def test_table_retains_empty_whitespace_and_plain_text():
    table = text_table("Table", rows=("", "First", " ", "Second"))
    assert text_values(table) == ("", "First", " ", "Second")
    assert not text_table("Empty").rows
    assert not hasattr(table, "choose")


def test_real_map_table_card_workflow_and_project_roundtrip(project, tmp_path, qtbot):
    app, project = project
    project.create_project(tmp_path / "world")
    image_path = tmp_path / "карта.png"
    image = QImage(400, 200, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.darkGreen)
    assert image.save(str(image_path))
    app.maps.import_map(image_path, "World map")
    qtbot.waitUntil(lambda: not app.maps.importing)
    document = next(iter(app.maps_service.maps.values()))
    map_window = app.window_manager.find_window(f"map:{document.id}")
    first = app.create_card("First")
    second = app.create_card("Second")
    first_editor = app.open_card_editor(first.id).widget()
    second_editor = app.open_card_editor(second.id).widget()
    first_editor.text_edit.insertPlainText("First content")
    second_editor.text_edit.insertPlainText("Second content")
    one = app.maps_service.add_token(document.id, first.id, 0.1, 0.2)
    app.maps_service.add_token(document.id, first.id, 0.8, 0.5)
    app.maps._token_action(document.id, one.id, "open")
    assert app.open_card_editor(first.id).widget() is first_editor
    table = app.tables_service.create_table("Encounters")
    table_window = app.tables.open_table(table.id)
    widget = table_window.widget()
    widget.model.apply(replace(table, rows=record_rows(table, ("Goblin", "Dragon"))))
    widget.table.selectRow(1)
    widget.copy_selection()
    assert QApplication.clipboard().text() == "Dragon"
    dice = app.dice.open().widget()
    dice.counts[20].setValue(0)
    dice.counts[4].setValue(1)
    dice.modifier.setValue(3)
    dice.roll.click()
    dice.copy.click()
    qtbot.waitUntil(lambda: QApplication.clipboard().text() == dice.result.toPlainText())
    assert len(app.window_manager.window_keys()) == 5
    assert project.save_current()
    revision = project.store.load().revision
    project._save_ui_state()
    app.delete_card(first.id)
    assert not app.maps_service.get_map(document.id).tokens
    assert not map_window.widget().view._tokens
    assert project.save_current()
    assert project.store.load().revision > revision
    before = project.store.load()
    root = project.store.root
    another = SQLiteProjectStore.create(tmp_path / "other")
    another.close()
    project.open_project(tmp_path / "other")
    assert not app.maps_service.maps and not app.tables_service.tables
    project.open_project(root)
    assert tuple(app.maps_service.maps.values()) == before.maps
    assert tuple(app.tables_service.tables.values()) == before.tables
    assert html_text(app.cards.get(second.id).content).strip() == "Second content"
    qtbot.waitUntil(lambda: "Колесо" in app.maps.open_map(document.id).widget().message.text())
    assert app.maps.open_map(document.id).widget().view.map_width == 400
    assert not project.saver.dirty


def test_live_table_editor_is_in_ctrl_s_snapshot(project, tmp_path, qtbot):
    app, project = project
    app.window.show()
    project.create_project(tmp_path / "world")
    table = app.tables_service.create_table("Table")
    app.tables_service.edit_table(table.id, rows=record_rows(table, ("Original",)))
    widget = app.tables.open_table(table.id).widget()
    widget.table.edit(widget.model.index(0, 0))
    editor = widget.table.findChild(QLineEdit)
    assert editor is not None
    editor.selectAll()
    qtbot.keyClicks(editor, "Live text")
    assert project.save_current()
    assert text_values(project.store.load().tables[0]) == ("Live text",)


def test_table_display_and_clipboard_preserve_literal_markup(project):
    app, project = project
    table = app.tables_service.create_table("Literal text")
    app.tables_service.edit_table(table.id, rows=record_rows(table, ("<b>Text</b>",)))
    widget = app.tables.open_table(table.id).widget()
    assert widget.model.data(widget.model.index(0, 0)) == "<b>Text</b>"
    widget.table.selectRow(0)
    widget.copy_selection()
    assert QApplication.clipboard().text() == "<b>Text</b>"


def test_missing_map_image_remains_editable_and_keeps_links(project, tmp_path, qtbot):
    app, project = project
    project.create_project(tmp_path / "world")
    source = tmp_path / "image.png"
    image = QImage(10, 10, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.black)
    image.save(str(source))
    asset = project.store.import_asset(source)
    project.assets[asset.id] = asset
    document = app.maps_service.create_map("Map", asset.id)
    app.maps_service.edit_map(document.id, tokens=(TokenInstance(str(uuid4()), 0.5, 0.5),))
    (project.store.root / asset.path).unlink()
    widget = app.maps.open_map(document.id).widget()
    qtbot.waitUntil(lambda: "недоступно" in widget.message.text())
    assert len(widget.view._tokens) == 1
    assert "Разорванная" in widget.view._tokens[0].toolTip()


def test_map_image_policy_rejects_svg_in_production_decoder(tmp_path):
    svg = tmp_path / "image.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>')
    store = SQLiteProjectStore.create(tmp_path / "world")
    try:
        asset = store.import_asset(svg)
        with pytest.raises(ValueError, match="Поддерживаются"):
            ensure_pyramid(store.root, asset)
        assert not store.load().maps
    finally:
        store.close()


def test_card_placement_rename_move_delete_undo_and_cascade(project, tmp_path, monkeypatch):
    app, project = project
    session = app.maps_service
    document = session.create_map("Map", str(uuid4()))
    card = app.create_card("Canonical")
    pin = session.add_token(document.id, card.id, 0.2, 0.3)
    other = session.create_map("Other", document.asset_id)
    second = session.add_token(other.id, card.id, 0.7, 0.8)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Renamed", True))
    app.maps._token_action(document.id, pin.id, "rename")
    assert app.cards.get(card.id).title == "Canonical"
    app.cards_service.update_card_fields(card.id, {"title": "Renamed"})
    assert app.cards.get(card.id).title == "Renamed"
    assert session.get_map(other.id).tokens == (second,)
    session.edit_token(document.id, pin.id, label_override="Local", x=0.6)
    session.undo_stack(document.id).undo()
    assert session.get_map(document.id).tokens == (pin,)
    app.maps._token_action(document.id, pin.id, "delete")
    assert app.cards.get(card.id) and not session.get_map(document.id).tokens
    session.undo_stack(document.id).undo()
    assert session.placement_count({card.id}) == 2
    app.delete_card(card.id)
    assert not session.get_map(document.id).tokens and not session.get_map(other.id).tokens
    session.undo_stack(document.id).redo()
    session.undo_stack(document.id).undo()
    assert not session.get_map(document.id).tokens
    with pytest.raises(ValueError):
        session.add_token(other.id, card.id, 0, 0)


def test_failed_image_import_does_not_publish_map_or_asset(project, tmp_path, qtbot, monkeypatch):
    app, project = project
    project.create_project(tmp_path / "world")
    bad = tmp_path / "not-image.png"
    bad.write_bytes(b"not an image")
    errors = []
    monkeypatch.setattr(app.maps, "_error", errors.append)
    app.maps.import_map(bad, "Rejected")
    qtbot.waitUntil(lambda: not app.maps.importing)
    assert errors and not app.maps_service.maps and not project.assets
    assert not project.saver.dirty


def test_all_modules_backup_restore_and_future_payload_is_preserved(tmp_path):
    source = tmp_path / "image.bin"
    source.write_bytes(b"image bytes")
    store = SQLiteProjectStore.create(tmp_path / "world")
    asset = store.import_asset(source)
    document = MapDocument("Map", asset.id, tokens=(TokenInstance(str(uuid4()), 0.1, 0.2),))
    table = text_table("Table", rows=("One", "Two"))
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
