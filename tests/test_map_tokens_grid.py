import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog

from lodandsy.application.module_session import ModuleSession
from lodandsy.application.sqlite_project_store import (
    ProjectError,
    ProjectSnapshot,
    SQLiteProjectStore,
    connect_database,
)
from lodandsy.domain.map_document import MapDocument, MapGrid, MapPin, MapToken
from lodandsy.ui.map_settings_dialogs import MapGridDialog, TokenPropertiesDialog

pytest_plugins = ["tests.project_fixture"]


def image_file(path, width=500, height=400):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.darkCyan)
    assert image.save(str(path))
    return path


def open_map(app, project, tmp_path, qtbot):
    project.create_project(tmp_path / "world")
    app.modules.import_map(image_file(tmp_path / "map.png"), "Map")
    qtbot.waitUntil(lambda: not app.modules.importing, timeout=15000)
    document = next(iter(app.modules.session.maps.values()))
    widget = app.modules.open_map(document.id).widget()
    qtbot.waitUntil(lambda: widget.token_add.isEnabled(), timeout=15000)
    return document, widget


@pytest.mark.parametrize("field,value", [("x", float("nan")), ("y", -1), ("width", 0),
    ("height", float("inf")), ("z", True), ("z", 10001), ("asset_id", "bad"), ("card_id", "bad")])
def test_token_invariants_reject_invalid_geometry_and_ids(field, value):
    token = MapToken("Token", str(uuid4()), 10, 20)
    with pytest.raises(ValueError):
        replace(token, **{field: value})


def test_grid_snap_undo_resize_does_not_move_tokens_and_pin_is_independent(qapp):
    session = ModuleSession()
    document = session.create_map("Map", str(uuid4()))
    pin = session.add_pin(document.id, "M1", .2, .3)
    token = session.add_token(document.id, "Token", str(uuid4()), 105, 130)
    grid = MapGrid(True, 50, 10, 15, .5, True)
    session.edit_map(document.id, grid=grid)
    assert session.get_map(document.id).tokens[0] == token
    session.move_token(document.id, token.id, 120, 140, bounds=(500, 400))
    moved = session.get_map(document.id).tokens[0]
    assert (moved.x, moved.y) == (135, 140)
    session.undo_stack(document.id).undo()
    assert session.get_map(document.id).tokens[0] == token
    session.undo_stack(document.id).redo()
    session.edit_map(document.id, grid=replace(grid, cell_size=100))
    assert session.get_map(document.id).tokens[0] == moved
    assert session.get_map(document.id).pins == (pin,)
    session.delete_token(document.id, token.id)
    session.undo_stack(document.id).undo()
    assert session.get_map(document.id).tokens == (moved,)
    with pytest.raises(ValueError, match="Duplicate"):
        replace(session.get_map(document.id), tokens=(replace(token, id=pin.id),))


def test_module_object_ids_cannot_change_during_edit_or_collide(qapp, monkeypatch):
    session = ModuleSession()
    document = session.create_map("Map", str(uuid4()))
    pin = session.add_pin(document.id, "Pin", .2, .3)
    token = session.add_token(document.id, "Token", str(uuid4()), 10, 20)
    table = session.create_table("Table")
    for operation in [lambda: session.edit_map(document.id, id=str(uuid4())),
                      lambda: session.edit_pin(document.id, pin.id, id=str(uuid4())),
                      lambda: session.edit_token(document.id, token.id, id=str(uuid4())),
                      lambda: session.edit_table(table.id, id=str(uuid4()))]:
        with pytest.raises(ValueError):
            operation()
    monkeypatch.setattr("lodandsy.domain.map_document.uuid4", lambda: document.id)
    with pytest.raises(ValueError, match="Duplicate"):
        session.create_map("Collision", document.asset_id)
    assert session.get_map(document.id).title == "Map"
    assert session.get_table(table.id) == table


def test_ui_import_properties_links_and_missing_image(project, qtbot, tmp_path, monkeypatch):
    app, project = project
    app.window.show()
    document, widget = open_map(app, project, tmp_path, qtbot)
    card = app.create_card("Card")
    source = image_file(tmp_path / "token.png", 30, 30)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(source), ""))
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Token", True))
    widget.token_add.trigger()
    qtbot.waitUntil(lambda: not app.card_images.importing)
    first = app.modules.session.get_map(document.id).tokens[0]
    assert len(project.assets) == 2
    def properties():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, TokenPropertiesDialog)
        dialog.title.setText("Renamed")
        dialog.width.setValue(80)
        dialog.height.setValue(96)
        dialog.z.setValue(7)
        dialog.card.setCurrentIndex(dialog.card.findData(card.id))
        dialog.accept()
    QTimer.singleShot(0, properties)
    app.modules._token_action(document.id, first.id, "properties")
    first = app.modules.session.get_map(document.id).tokens[0]
    assert (first.title, first.width, first.height, first.z, first.card_id) == (
        "Renamed", 80, 96, 7, card.id)
    app.modules.import_token(document.id, source, "Second", 200, 200)
    qtbot.waitUntil(lambda: not app.card_images.importing)
    second = app.modules.session.get_map(document.id).tokens[1]
    app.modules.session.edit_token(document.id, second.id, card_id=card.id)
    assert first.asset_id == second.asset_id and len(project.assets) == 2
    app.modules._token_action(document.id, first.id, "open")
    assert app.card_editor_window_key(card.id) in app.window_manager.window_keys()
    app.delete_card(card.id)
    assert len(app.modules.session.get_map(document.id).tokens) == 2
    assert all("Разорванная" in item.toolTip() for item in widget.view._tokens)
    asset = project.assets[first.asset_id]
    qtbot.waitUntil(lambda: not app.card_images._pending)
    (project.store.root / asset.path).unlink()
    qtbot.wait(260)  # Bounded token lookup TTL; no image copies are retained outside the LRU.
    canvas = QImage(600, 400, QImage.Format.Format_RGB32)
    painter = QPainter(canvas)
    widget.view.render(painter)
    painter.end()
    assert len(app.modules.session.get_map(document.id).tokens) == 2
    assert any("Изображение" in item.toolTip() for item in widget.view._tokens)


def test_grid_dialog_render_and_selection_do_not_snap_existing_tokens(project, qtbot, tmp_path):
    app, project = project
    app.window.show()
    document, widget = open_map(app, project, tmp_path, qtbot)
    token = app.modules.session.add_token(document.id, "Token", document.asset_id, 123, 137)
    def configure():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, MapGridDialog)
        dialog.enabled.setChecked(True)
        dialog.cell.setValue(50)
        dialog.x.setValue(10)
        dialog.snap.setChecked(True)
        dialog.accept()
    QTimer.singleShot(0, configure)
    widget.grid_requested.emit()
    assert app.modules.session.get_map(document.id).tokens[0] == token
    view = widget.view
    view.resetTransform()
    view.scale(1.5, 1.5)
    view.centerOn(token.x, token.y)
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                     pos=view.mapFromScene(token.x, token.y))
    qtbot.wait(30)
    assert app.modules.session.get_map(document.id).tokens[0] == token
    canvas = QImage(600, 400, QImage.Format.Format_RGB32)
    painter = QPainter(canvas)
    view.render(painter)
    painter.end()
    assert 0 < view._grid.last_line_count < 2048
    assert project.save_current()
    view.resetTransform()
    view.scale(.001, .001)
    assert app.modules.session.get_map(document.id).tokens[0] == token
    assert not project.saver.dirty


def test_annotation_updates_reuse_items_and_noop_snap_restores_view(project, qtbot, tmp_path):
    app, project = project
    document, widget = open_map(app, project, tmp_path, qtbot)
    token = app.modules.session.add_token(document.id, "Token", document.asset_id, 135, 135)
    item = widget.view._tokens[0]
    app.modules.session.edit_map(document.id, grid=MapGrid(True, 50, 10, 10, .5, True))
    assert widget.view._tokens[0] is item
    count = app.modules.session.undo_stack(document.id).count()
    item.setPos(140, 141)
    widget.view.token_moved.emit(token.id, 140, 141)
    assert app.modules.session.undo_stack(document.id).count() == count
    assert item.pos().x() == item.pos().y() == 135
    app.modules.session.edit_token(document.id, token.id, title="Renamed", width=96)
    assert widget.view._tokens[0] is item and item.boundingRect().width() == 96


def test_user_titles_stay_plain_in_graphics_tooltips(project, qtbot, tmp_path):
    app, project = project
    document, widget = open_map(app, project, tmp_path, qtbot)
    title = '<img src="https://example.com/no-network.png">'
    token = app.modules.session.add_token(document.id, title, document.asset_id, 50, 50)
    app.modules.session.add_pin(document.id, title, .5, .5)
    assert "<img" not in widget.view._tokens[0].toolTip()
    assert "&lt;img" in widget.view._tokens[0].toolTip()
    assert "&lt;img" in widget.view._pins[0].toolTip()
    assert app.modules.session.get_map(document.id).tokens[0].title == token.title == title


@pytest.mark.parametrize("zoom", [.5, 2])
def test_drag_world_coordinates_and_snap_are_independent_of_zoom(project, qtbot, tmp_path, zoom):
    app, project = project
    app.window.show()
    document, widget = open_map(app, project, tmp_path, qtbot)
    token = app.modules.session.add_token(document.id, "Token", document.asset_id, 120, 130)
    app.modules.session.edit_map(document.id, grid=MapGrid(True, 50, 10, 10, .5, True))
    view = widget.view
    view.resetTransform()
    view.scale(zoom, zoom)
    view.centerOn(150, 150)
    start = view.mapFromScene(120, 130)
    end = view.mapFromScene(190, 190)
    qtbot.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(view.viewport(), pos=end, delay=20)
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    qtbot.waitUntil(lambda: app.modules.session.get_map(document.id).tokens[0].x != token.x)
    moved = app.modules.session.get_map(document.id).tokens[0]
    assert (moved.x, moved.y) == (185, 185)
    app.modules.session.undo_stack(document.id).undo()
    assert app.modules.session.get_map(document.id).tokens[0] == token


def make_v3(root, source):
    store = SQLiteProjectStore.create(root)
    asset = store.import_asset(source)
    pin = MapPin("Old pin", .2, .4, card_id=str(uuid4()))
    document = MapDocument("Old map", asset.id, pins=(pin,))
    store.save(ProjectSnapshot((), 1, (asset,), (document,)))
    path = store.path
    store.close()
    with closing(connect_database(path)) as connection, connection:
        connection.execute("ALTER TABLE map_document DROP COLUMN tokens")
        connection.execute("ALTER TABLE map_document DROP COLUMN grid")
        connection.execute("UPDATE map_document SET payload_version=1")
        connection.execute("PRAGMA user_version=3")
    return path, document


def test_v3_migration_backup_and_v4_roundtrip_broken_links(tmp_path):
    path, old = make_v3(tmp_path / "world", image_file(tmp_path / "a.png"))
    store = SQLiteProjectStore.open(path.parent)
    assert store.load().maps == (old,)
    backup = next((store.root / "backups").glob("schema-v3-*.sqlite3"))
    with closing(sqlite3.connect(backup)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (3,)
    token = MapToken("Missing asset and card", str(uuid4()), 12, 34, card_id=str(uuid4()))
    document = replace(old, tokens=(token,), grid=MapGrid(True, 70, -10, 15, .6, True))
    snapshot = replace(store.load(), maps=(document,), revision=2)
    store.save(snapshot)
    bundle = tmp_path / "backup.lodbackup"
    store.backup(bundle)
    restored = SQLiteProjectStore.restore(bundle, tmp_path / "restored")
    assert restored.load() == snapshot
    restored.close()
    store.close()


def test_v3_migration_rollback_and_unknown_payload_preserved(tmp_path, monkeypatch):
    path, _ = make_v3(tmp_path / "world", image_file(tmp_path / "a.png"))
    original = SQLiteProjectStore._upgrade_v3
    def fail(connection):
        original(connection)
        raise sqlite3.OperationalError("interrupted")
    monkeypatch.setattr(SQLiteProjectStore, "_upgrade_v3", staticmethod(fail))
    with pytest.raises(ProjectError, match="original schema retained"):
        SQLiteProjectStore.open(path.parent)
    with closing(connect_database(path)) as connection, connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (3,)
        columns = [row[1] for row in connection.execute("PRAGMA table_info(map_document)")]
        assert "tokens" not in columns
        connection.execute("UPDATE map_document SET payload_version=999")
    before = path.read_bytes()
    with pytest.raises(ProjectError, match="Unsupported Map"):
        SQLiteProjectStore.open(path.parent)
    assert path.read_bytes() == before


def test_future_grid_fields_refuse_load_without_overwriting(tmp_path):
    path, _ = make_v3(tmp_path / "world", image_file(tmp_path / "a.png"))
    store = SQLiteProjectStore.open(path.parent)
    store.close()
    with closing(connect_database(path)) as connection, connection:
        connection.execute("UPDATE map_document SET grid=?", (json.dumps({"future": True}),))
    before = path.read_bytes()
    with pytest.raises(ProjectError):
        SQLiteProjectStore.open(path.parent)
    assert path.read_bytes() == before
