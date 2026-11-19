import random
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit

from lodandsy.application.map_pyramid import ensure_pyramid
from lodandsy.application.module_session import ModuleSession
from lodandsy.application.rich_html import html_text
from lodandsy.application.sqlite_project_store import (
    ProjectError,
    ProjectSnapshot,
    SQLiteProjectStore,
    connect_database,
)
from lodandsy.domain.card import Card
from lodandsy.domain.dice_document import roll_dice
from lodandsy.domain.map_document import MapDocument, TokenInstance
from tests.project_fixture import record_rows, text_table, text_values

pytest_plugins = ["tests.project_fixture"]


def test_dice_details_total_and_repeatable_randomness():
    from lodandsy.domain.dice_document import DiceConfig

    result = roll_dice(DiceConfig((0, 3, 0, 0, 0, 0, 0), -2), random.Random(4))
    assert result.groups == ((6, (2, 3, 1)),)
    assert result.total == 4 and result.modifier == -2
    assert "Итог = 4" in result.text()


def test_map_validation_undo_noops_and_immutable_state(qapp):
    session = ModuleSession()
    document = session.create_map("Map", str(uuid4()))
    pin = session.add_card_placement(Card("Point"), document.id, 0.2, 0.3)
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


def test_random_table_choice_and_empty_behavior():
    table = text_table("Table", rows=("", "First", " ", "Second"))
    index, row = table.choose(random.Random(1))
    assert index == 2 and row.value(table.columns[0].id) == "First"
    with pytest.raises(ValueError):
        text_table("Empty").choose()


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
    one = app.modules.session.add_token(document.id, first.id, 0.1, 0.2)
    app.modules.session.add_token(document.id, first.id, 0.8, 0.5)
    app.modules._token_action(document.id, one.id, "open")
    assert app.open_card_editor(first.id).widget() is first_editor
    table = app.modules.session.create_table("Encounters")
    table_window = app.modules.open_table(table.id)
    widget = table_window.widget()
    widget.model.apply(replace(table, rows=record_rows(table, ("Goblin", "Dragon"))))
    widget.roll_requested.click()
    widget.copy.click()
    assert QApplication.clipboard().text() == widget.result.text()
    dice = app.modules.open_dice().widget()
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
    assert not app.modules.session.get_map(document.id).tokens
    assert not map_window.widget().view._tokens
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
    assert html_text(app.cards.get(second.id).content).strip() == "Second content"
    qtbot.waitUntil(lambda: "Колесо" in app.modules.open_map(document.id).widget().message.text())
    assert app.modules.open_map(document.id).widget().view.map_width == 400
    assert not project.saver.dirty


def test_live_table_editor_is_in_ctrl_s_snapshot(project, tmp_path, qtbot):
    app, project = project
    app.window.show()
    project.create_project(tmp_path / "world")
    table = app.modules.session.create_table("Table")
    app.modules.session.edit_table(table.id, rows=record_rows(table, ("Original",)))
    widget = app.modules.open_table(table.id).widget()
    widget.table.edit(widget.model.index(0, 0))
    editor = widget.table.findChild(QLineEdit)
    assert editor is not None
    editor.selectAll()
    qtbot.keyClicks(editor, "Live text")
    assert project.save_current()
    assert text_values(project.store.load().tables[0]) == ("Live text",)


def test_random_table_result_preserves_literal_markup(project):
    app, project = project
    table = app.modules.session.create_table("Literal text")
    app.modules.session.edit_table(table.id, rows=record_rows(table, ("<b>Text</b>",)))
    widget = app.modules.open_table(table.id).widget()
    widget.roll_requested.click()
    widget.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    widget.result.setSelection(0, len(widget.result.text()))
    assert widget.result.selectedText() == "1. Вариант: <b>Text</b>"


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
    app.modules.session.edit_map(document.id, tokens=(TokenInstance(str(uuid4()), 0.5, 0.5),))
    (project.store.root / asset.path).unlink()
    widget = app.modules.open_map(document.id).widget()
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
    session = app.modules.session
    document = session.create_map("Map", str(uuid4()))
    card = app.create_card("Canonical")
    pin = session.add_token(document.id, card.id, 0.2, 0.3)
    other = session.create_map("Other", document.asset_id)
    second = session.add_token(other.id, card.id, 0.7, 0.8)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Renamed", True))
    app.modules._token_action(document.id, pin.id, "rename")
    assert app.cards.get(card.id).title == "Renamed"
    assert session.get_map(other.id).tokens == (second,)
    session.edit_token(document.id, pin.id, label_override="Local", x=0.6)
    session.undo_stack(document.id).undo()
    assert session.get_map(document.id).tokens == (pin,)
    app.modules._token_action(document.id, pin.id, "delete")
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
    monkeypatch.setattr(app.modules, "_error", errors.append)
    app.modules.import_map(bad, "Rejected")
    qtbot.waitUntil(lambda: not app.modules.importing)
    assert errors and not app.modules.session.maps and not project.assets
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
