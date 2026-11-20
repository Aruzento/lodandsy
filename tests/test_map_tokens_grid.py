import json
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from lodandsy.application.sqlite_project_store import (
    ProjectError,
    ProjectSnapshot,
    SQLiteProjectStore,
    connect_database,
)
from lodandsy.domain.card import Card
from lodandsy.domain.map_document import MapDocument, MapGrid, TokenInstance, resolve_token
from lodandsy.ui.map_settings_dialogs import MapGridDialog
from lodandsy.ui.map_widget import MapView
from tests.project_fixture import map_services

pytest_plugins = ["tests.project_fixture"]


def image_file(path, width=500, height=400):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.darkCyan)
    assert image.save(str(path))
    return path


def open_map(app, project, tmp_path, qtbot):
    project.create_project(tmp_path / "world")
    app.maps.import_map(image_file(tmp_path / "map.png"), "Map")
    qtbot.waitUntil(lambda: not app.maps.importing, timeout=15000)
    document = next(iter(app.maps_service.maps.values()))
    widget = app.maps.open_map(document.id).widget()
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
        ("image_override", "bad"),
        ("card_id", "bad"),
    ],
)
def test_token_invariants_reject_invalid_geometry_and_ids(field, value):
    token = TokenInstance(str(uuid4()), 10, 20)
    with pytest.raises(ValueError):
        replace(token, **{field: value})


def test_grid_undo_resize_does_not_move_tokens_and_other_token_is_independent(qapp):
    session, actions, tables, cards_service = map_services()
    document = session.create_map("Map", str(uuid4()))
    pin = actions.add_card_placement(Card("M1"), document.id, 0.2, 0.3)
    token = actions.add_card_placement(Card("Token"), document.id, 105, 130)
    grid = MapGrid(True, 50, 10, 15, 0.5)
    session.edit_map(document.id, grid=grid)
    assert session.get_map(document.id).tokens[1] == token
    session.move_token(document.id, token.id, 120, 140, bounds=(500, 400))
    moved = session.get_map(document.id).tokens[1]
    assert (moved.x, moved.y) == (120, 140)
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
    session, actions, tables, cards_service = map_services()
    document = session.create_map("Map", str(uuid4()))
    pin = actions.add_card_placement(Card("Pin"), document.id, 0.2, 0.3)
    token = actions.add_card_placement(Card("Token"), document.id, 10, 20)
    table = tables.create_table("Table")
    with pytest.raises(ValueError, match="отсутствует"):
        session.move_token(document.id, str(uuid4()), 0, 0)
    for operation in [
        lambda: session.edit_map(document.id, id=str(uuid4())),
        lambda: session.edit_token(document.id, pin.id, id=str(uuid4())),
        lambda: session.edit_token(document.id, token.id, id=str(uuid4())),
        lambda: tables.edit_table(table.id, id=str(uuid4())),
    ]:
        with pytest.raises(ValueError):
            operation()
    monkeypatch.setattr("lodandsy.domain.map_document.uuid4", lambda: document.id)
    with pytest.raises(ValueError, match="Duplicate"):
        session.create_map("Collision", document.asset_id)
    assert session.get_map(document.id).title == "Map"
    assert tables.get_table(table.id) == table


def test_ui_import_properties_canonical_images_and_multi_map(project, qtbot, tmp_path):
    app, project = project
    document, widget = open_map(app, project, tmp_path, qtbot)
    source = image_file(tmp_path / "token.png", 30, 30)
    app.maps.create_card_token(document.id, source, "Canonical", 100, 100)
    qtbot.waitUntil(lambda: not app.media.importing)
    first = app.maps_service.get_map(document.id).tokens[0]
    card = app.cards.get(first.card_id)
    app.maps_service.add_token(document.id, card.id, 200, 200)
    other = app.maps_service.create_map("Other", document.asset_id)
    app.maps_service.add_token(other.id, card.id, 200, 200)
    second_widget = app.maps.open_map(other.id).widget()
    app.cards_service.update_card_fields(card.id, {"title": "Renamed", "hp": 0, "summary": "HP 0"})
    assert all(i.presentation.label == "Renamed" for i in widget.view._tokens)
    assert second_widget.view._tokens[0].presentation.label == "Renamed"
    app.cards_service.update_card_fields(card.id, {"hp": 17})
    assert "HP: 17" in second_widget.view._tokens[0].presentation.summary
    app.cards_service.update_card(card.id, portrait=None)
    assert second_widget.view._tokens[0].presentation.asset_id is None

    app.maps_service.edit_token(document.id, first.id, label_override="Local", cells_w=2, cells_h=3)
    assert widget.view._tokens[0].presentation.label == "Local"
    assert widget.view._tokens[1].presentation.label == "Renamed"
    assert len(project.assets) == 2
    app.maps._token_action(document.id, first.id, "open")
    assert app.window_manager.find_window(app.card_editor_window_key(card.id))
    assert project.save_current()
    assert project.store.load().maps[0].tokens[0].card_id == card.id
    app.delete_card(card.id)
    assert not widget.view._tokens and not second_widget.view._tokens


def test_grid_dialog_render_and_selection_do_not_snap_existing_tokens(project, qtbot, tmp_path):
    app, project = project
    app.window.show()
    document, widget = open_map(app, project, tmp_path, qtbot)
    token = app.maps_service.add_token(document.id, app.create_card("Token").id, 123, 137)

    def configure():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, MapGridDialog)
        dialog.enabled.setChecked(True)
        dialog.cell.setValue(50)
        dialog.x.setValue(10)
        dialog.accept()

    QTimer.singleShot(0, configure)
    widget.grid_requested.emit()
    assert app.maps_service.get_map(document.id).tokens[0] == token
    view = widget.view
    view.resetTransform()
    view.scale(1.5, 1.5)
    view.centerOn(token.x, token.y)
    qtbot.mouseClick(
        view.viewport(), Qt.MouseButton.LeftButton, pos=view.mapFromScene(token.x, token.y)
    )
    qtbot.wait(30)
    assert app.maps_service.get_map(document.id).tokens[0] == token
    canvas = QImage(600, 400, QImage.Format.Format_RGB32)
    painter = QPainter(canvas)
    view.render(painter)
    painter.end()
    assert 0 < view._grid.last_line_count < 2048
    assert project.save_current()
    view.resetTransform()
    view.scale(0.001, 0.001)
    assert app.maps_service.get_map(document.id).tokens[0] == token
    assert not project.saver.dirty


def test_annotation_updates_reuse_items_and_free_movement(project, qtbot, tmp_path):
    app, project = project
    document, widget = open_map(app, project, tmp_path, qtbot)
    token = app.maps_service.add_token(document.id, app.create_card("Token").id, 135, 135)
    item = widget.view._tokens[0]
    app.maps_service.edit_map(document.id, grid=MapGrid(True, 50, 10, 10, 0.5))
    assert widget.view._tokens[0] is item
    count = app.maps_service.undo_stack(document.id).count()
    item.setPos(140, 141)
    widget.view.token_moved.emit(token.id, 140, 141)
    assert app.maps_service.undo_stack(document.id).count() == count + 1
    assert (item.pos().x(), item.pos().y()) == (140, 141)
    app.maps_service.edit_token(document.id, token.id, label_override="Renamed", cells_w=2)
    assert widget.view._tokens[0] is item and item.boundingRect().width() == 100


def test_user_titles_stay_plain_in_graphics_tooltips(project, qtbot, tmp_path):
    app, project = project
    document, widget = open_map(app, project, tmp_path, qtbot)
    title = '<img src="https://example.com/no-network.png">'
    token = app.maps_service.add_token(document.id, app.create_card(title).id, 50, 50)
    app.maps_service.add_token(document.id, token.card_id, 0.5, 0.5)
    assert "<img" not in widget.view._tokens[0].toolTip()
    assert "&lt;img" in widget.view._tokens[0].toolTip()
    assert "&lt;img" in widget.view._tokens[0].toolTip()
    assert app.cards.get(token.card_id).title == title


@pytest.mark.parametrize("zoom", [0.5, 2])
def test_drag_world_coordinates_are_independent_of_zoom(project, qtbot, tmp_path, zoom):
    app, project = project
    app.window.show()
    document, widget = open_map(app, project, tmp_path, qtbot)
    token = app.maps_service.add_token(document.id, app.create_card("Token").id, 120, 130)
    app.maps_service.edit_map(document.id, grid=MapGrid(True, 50, 10, 10, 0.5))
    view = widget.view
    view.resetTransform()
    view.scale(zoom, zoom)
    view.centerOn(150, 150)
    start = view.mapFromScene(120, 130)
    end = view.mapFromScene(190, 190)
    qtbot.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(view.viewport(), pos=end, delay=20)
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    qtbot.waitUntil(lambda: app.maps_service.get_map(document.id).tokens[0].x != token.x)
    moved = app.maps_service.get_map(document.id).tokens[0]
    assert moved.x == pytest.approx(190, abs=2 / zoom)
    assert moved.y == pytest.approx(190, abs=2 / zoom)
    app.maps_service.undo_stack(document.id).undo()
    assert app.maps_service.get_map(document.id).tokens[0] == token


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
    view.set_annotations(document, lambda key: None, None, {}, lambda *a: None)
    image = QImage(80, 40, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.red)

    def provider(*args):
        return image

    card = Card("Person", card_type="character")
    character = TokenInstance(card.id, 0, 0)
    for kind in ("character", "item"):
        token = replace(character, kind_override=kind)
        item = TokenItem(token, resolve_token(token, card), view, None, "test.png", provider)
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
        resized = replace(token, cells_w=2, cells_h=3)
        item.set_value(resized, resolve_token(resized, card), None, None, provider)
        assert (item.boundingRect().width(), item.boundingRect().height()) == (128, 192)
    assert not hasattr(MapGrid(), "snap_point")


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
    assert app.maps_service.get_map(document.id) == document


def test_tree_card_drop_creates_placement_without_reparent_and_rejects_other_kinds(
    project, qtbot, tmp_path
):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QDragEnterEvent, QDropEvent

    app, project = project
    document, widget = open_map(app, project, tmp_path, qtbot)
    card = app.create_card("Drag Card")
    model = app.window.tree_panel.tree_model
    view = widget.view
    position = view.mapFromScene(200, 200)
    mime = model.mimeData([model.index_for_node("card:" + card.id)])
    event = QDragEnterEvent(
        position,
        Qt.DropAction.MoveAction | Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.dragEnterEvent(event)
    assert event.isAccepted() and event.dropAction() == Qt.DropAction.CopyAction
    dropped = QDropEvent(
        QPointF(position),
        Qt.DropAction.MoveAction | Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    before = app.cards_service.entities.get(card.id)
    view.dropEvent(dropped)
    assert dropped.isAccepted() and app.cards_service.entities.get(card.id) == before
    assert app.maps_service.get_map(document.id).tokens[0].card_id == card.id
    for kind, key in [("map", document.id), ("card", card.id)]:
        view = widget.view if kind == "map" else app.maps.open_map_editor(document.id).widget().view
        mime = model.mimeData([model.index_for_node(kind + ":" + key)])
        event = QDragEnterEvent(
            position,
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        view.dragEnterEvent(event)
        assert not event.isAccepted()
    assert len(app.maps_service.get_map(document.id).tokens) == 1
