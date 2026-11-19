import json
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
from lodandsy.domain.map_document import MapDocument, MapGrid, MapToken
from lodandsy.ui.map_settings_dialogs import MapGridDialog, TokenPropertiesDialog
from lodandsy.ui.map_widget import MapView

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


@pytest.mark.parametrize(
    "field,value",
    [
        ("x", float("nan")),
        ("y", -1),
        ("cells_w", 0),
        ("cells_h", float("inf")),
        ("z", True),
        ("z", 10001),
        ("asset_id", "bad"),
        ("entity_id", "bad"),
    ],
)
def test_token_invariants_reject_invalid_geometry_and_ids(field, value):
    token = MapToken("Token", str(uuid4()), 10, 20)
    with pytest.raises(ValueError):
        replace(token, **{field: value})


def test_grid_snap_undo_resize_does_not_move_tokens_and_other_token_is_independent(qapp):
    session = ModuleSession()
    document = session.create_map("Map", str(uuid4()))
    pin = session.add_token(document.id, "M1", None, 0.2, 0.3)
    token = session.add_token(document.id, "Token", str(uuid4()), 105, 130)
    grid = MapGrid(True, 50, 10, 15, 0.5, True)
    session.edit_map(document.id, grid=grid)
    assert session.get_map(document.id).tokens[1] == token
    session.move_token(document.id, token.id, 120, 140, bounds=(500, 400))
    moved = session.get_map(document.id).tokens[1]
    assert (moved.x, moved.y) == (135, 140)
    session.undo_stack(document.id).undo()
    assert session.get_map(document.id).tokens[1] == token
    session.undo_stack(document.id).redo()
    session.edit_map(document.id, grid=replace(grid, cell_size=100))
    assert session.get_map(document.id).tokens[1] == moved
    assert session.get_map(document.id).tokens[0] == pin
    session.delete_token(document.id, token.id)
    session.undo_stack(document.id).undo()
    assert session.get_map(document.id).tokens == (pin, moved)
    with pytest.raises(ValueError, match="Duplicate"):
        replace(session.get_map(document.id), tokens=(pin, replace(token, id=pin.id)))


def test_module_object_ids_cannot_change_during_edit_or_collide(qapp, monkeypatch):
    session = ModuleSession()
    document = session.create_map("Map", str(uuid4()))
    pin = session.add_token(document.id, "Pin", None, 0.2, 0.3)
    token = session.add_token(document.id, "Token", str(uuid4()), 10, 20)
    table = session.create_table("Table")
    with pytest.raises(ValueError, match="отсутствует"):
        session.move_token(document.id, str(uuid4()), 0, 0)
    for operation in [
        lambda: session.edit_map(document.id, id=str(uuid4())),
        lambda: session.edit_token(document.id, pin.id, id=str(uuid4())),
        lambda: session.edit_token(document.id, token.id, id=str(uuid4())),
        lambda: session.edit_table(table.id, id=str(uuid4())),
    ]:
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
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: (a[3][0], True))
    widget.token_add.trigger()
    qtbot.waitUntil(lambda: not app.card_images.importing)
    first = app.modules.session.get_map(document.id).tokens[0]
    assert len(project.assets) == 2

    def properties():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, TokenPropertiesDialog)
        dialog.title.setText("Renamed")
        dialog.width.setValue(2)
        dialog.height.setValue(3)
        dialog.z.setValue(7)
        dialog.card.setCurrentIndex(dialog.card.findData(card.id))
        dialog.accept()

    QTimer.singleShot(0, properties)
    app.modules._token_action(document.id, first.id, "properties")
    first = app.modules.session.get_map(document.id).tokens[0]
    assert (first.title, first.cells_w, first.cells_h, first.z, first.entity_id) == (
        "Renamed",
        2,
        3,
        7,
        card.id,
    )
    app.modules.import_token(document.id, source, "Second", 200, 200)
    qtbot.waitUntil(lambda: not app.card_images.importing)
    second = app.modules.session.get_map(document.id).tokens[1]
    app.modules.session.edit_token(document.id, second.id, entity_id=card.id)
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
    qtbot.mouseClick(
        view.viewport(), Qt.MouseButton.LeftButton, pos=view.mapFromScene(token.x, token.y)
    )
    qtbot.wait(30)
    assert app.modules.session.get_map(document.id).tokens[0] == token
    canvas = QImage(600, 400, QImage.Format.Format_RGB32)
    painter = QPainter(canvas)
    view.render(painter)
    painter.end()
    assert 0 < view._grid.last_line_count < 2048
    assert project.save_current()
    view.resetTransform()
    view.scale(0.001, 0.001)
    assert app.modules.session.get_map(document.id).tokens[0] == token
    assert not project.saver.dirty


def test_annotation_updates_reuse_items_and_noop_snap_restores_view(project, qtbot, tmp_path):
    app, project = project
    document, widget = open_map(app, project, tmp_path, qtbot)
    token = app.modules.session.add_token(document.id, "Token", document.asset_id, 135, 135)
    item = widget.view._tokens[0]
    app.modules.session.edit_map(document.id, grid=MapGrid(True, 50, 10, 10, 0.5, True))
    assert widget.view._tokens[0] is item
    count = app.modules.session.undo_stack(document.id).count()
    item.setPos(140, 141)
    widget.view.token_moved.emit(token.id, 140, 141)
    assert app.modules.session.undo_stack(document.id).count() == count
    assert item.pos().x() == item.pos().y() == 135
    app.modules.session.edit_token(document.id, token.id, title="Renamed", cells_w=2)
    assert widget.view._tokens[0] is item and item.boundingRect().width() == 100


def test_user_titles_stay_plain_in_graphics_tooltips(project, qtbot, tmp_path):
    app, project = project
    document, widget = open_map(app, project, tmp_path, qtbot)
    title = '<img src="https://example.com/no-network.png">'
    token = app.modules.session.add_token(document.id, title, document.asset_id, 50, 50)
    app.modules.session.add_token(document.id, title, None, 0.5, 0.5)
    assert "<img" not in widget.view._tokens[0].toolTip()
    assert "&lt;img" in widget.view._tokens[0].toolTip()
    assert "&lt;img" in widget.view._tokens[0].toolTip()
    assert app.modules.session.get_map(document.id).tokens[0].title == token.title == title


@pytest.mark.parametrize("zoom", [0.5, 2])
def test_drag_world_coordinates_and_snap_are_independent_of_zoom(project, qtbot, tmp_path, zoom):
    app, project = project
    app.window.show()
    document, widget = open_map(app, project, tmp_path, qtbot)
    token = app.modules.session.add_token(document.id, "Token", document.asset_id, 120, 130)
    app.modules.session.edit_map(document.id, grid=MapGrid(True, 50, 10, 10, 0.5, True))
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


def test_future_grid_fields_refuse_load_without_overwriting(tmp_path):
    store = SQLiteProjectStore.create(tmp_path / "world")
    source = image_file(tmp_path / "image.png")
    asset = store.import_asset(source)
    document = MapDocument("Map", asset.id)
    store.save(ProjectSnapshot((), 1, (asset,), (document,)))
    with closing(connect_database(store.path)) as connection, connection:
        connection.execute("UPDATE map_document SET grid=?", (json.dumps({"future": True}),))
    before = store.path.read_bytes()
    with pytest.raises(ProjectError):
        store.load()
    assert store.path.read_bytes() == before
    store.close()


def test_character_circle_item_aspect_alpha_and_cell_footprint(qapp):
    from lodandsy.ui.map_annotations import TokenItem

    view = MapView()
    document = MapDocument("Map", str(uuid4()), grid=MapGrid(cell_size=64))
    view.set_annotations(document, set(), None, {}, lambda *a: None)
    image = QImage(80, 40, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.red)
    def provider(*args):
        return image
    character = MapToken("Person", None, 0, 0)
    for kind in ("character", "item"):
        token = replace(character, kind=kind)
        item = TokenItem(token, view, None, "test.png", provider, False)
        canvas = QImage(100, 100, QImage.Format.Format_ARGB32_Premultiplied)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.translate(50, 50)
        item.paint(painter, None)
        painter.end()
        assert canvas.pixelColor(20, 20).alpha() == 0
        assert canvas.pixelColor(50, 50).red() == 255
        if kind == "character":
            assert canvas.pixelColor(50, 18).green() > 200  # White circular border.
        else:
            assert canvas.pixelColor(50, 25).alpha() == 0  # Aspect fit, no frame.
        item.set_value(replace(token, cells_w=2, cells_h=3), None, None, provider, False)
        assert (item.boundingRect().width(), item.boundingRect().height()) == (128, 192)
    assert MapGrid(True, 50, 10, 15, snap=True).snap_point(120, 140, 2, 2) == (110, 165)


def test_far_grid_lod_stays_visible_without_mutating_world(project, qtbot, tmp_path):
    app, project = project
    document, widget = open_map(app, project, tmp_path, qtbot)
    assert document.grid.enabled
    view = widget.view
    view.resize(700, 500)
    view.resetTransform()
    view.scale(0.1, 0.1)
    canvas = QImage(700, 500, QImage.Format.Format_RGB32)
    painter = QPainter(canvas)
    view.render(painter)
    painter.end()
    assert view._grid.detail_factor >= 2 and view._grid.last_line_count > 0
    assert app.modules.session.get_map(document.id) == document
