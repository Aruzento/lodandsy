import pytest
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QMouseEvent, QPainterPath, QTransform
from PySide6.QtWidgets import QApplication

from lodandsy.ui.map_vectors import rotation_handle
from tests.test_map_presentation import render
from tests.test_map_tokens_grid import open_map

pytest_plugins = ["tests.project_fixture"]

LEFT = Qt.MouseButton.LeftButton
ALT = Qt.KeyboardModifier.AltModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier


def mouse_move(view, point, modifiers=Qt.KeyboardModifier.NoModifier):
    viewport = view.viewport()
    QApplication.sendEvent(viewport, QMouseEvent(
        QEvent.Type.MouseMove, QPointF(point), QPointF(viewport.mapToGlobal(point)),
        Qt.MouseButton.NoButton, LEFT, modifiers,
    ))


def world_mouse(view, kind, position, modifiers=Qt.KeyboardModifier.NoModifier):
    point = view.viewportTransform().map(position)
    viewport = view.viewport()
    QApplication.sendEvent(viewport, QMouseEvent(
        kind, point, QPointF(viewport.mapToGlobal(point.toPoint())),
        Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else LEFT,
        Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else LEFT,
        modifiers,
    ))


@pytest.mark.parametrize(
    "zoom,modifiers,corner,size,position",
    [
        (1, Qt.KeyboardModifier.NoModifier, "bottomRight", (2.75390625, 1.3671875),
         (209.125, 156.75)),
        (1.4, ALT, "topLeft", (2.75390625, 1.376953125), (160.875, 132.9375)),
        (0.7, SHIFT, "bottomRight", (3.5078125, 1.734375), (185, 145)),
        (1.4, ALT | SHIFT, "bottomRight", (3.5078125, 1.75390625), (185, 145)),
    ],
)
def test_object_resize_uses_corner_or_center_and_commits_one_undo(
    project, tmp_path, qtbot, zoom, modifiers, corner, size, position,
):
    app, projects = project
    document, viewer = open_map(app, projects, tmp_path, qtbot)
    card = app.create_card("Ящик", card_type="object")
    app.cards_service.update_card_fields(card.id, {"token_cells_w": 2})
    token = app.actions.place_card(document.id, card.id, 185, 145)
    other = app.actions.place_card(document.id, card.id, 375, 265)
    view = viewer.view
    view.resetTransform()
    view.scale(zoom, zoom)
    view.centerOn(token.x, token.y)
    viewport = view.viewport()
    qtbot.mouseClick(viewport, LEFT, pos=view.mapFromScene(QPointF(token.x, token.y)))
    assert view.selected_token_id() == token.id
    item = view._tokens[0]
    rect = item.sceneBoundingRect()
    anchor = getattr(rect, corner)()
    direction = -1 if corner == "topLeft" else 1
    end = anchor + QPointF(48.25, 23.5) * direction
    stack = app.maps_service.undo_stack(document.id)
    index, revision = stack.index(), projects.saver.revision
    world_mouse(view, QEvent.Type.MouseButtonPress, anchor, modifiers)
    world_mouse(view, QEvent.Type.MouseMove, end, modifiers)
    assert item.transform_preview is not None
    assert (item.transform_preview.cells_w, item.transform_preview.cells_h) == pytest.approx(size)
    assert app.maps_service.get_map(document.id).tokens == (token, other)
    assert stack.index() == index and projects.saver.revision == revision
    world_mouse(view, QEvent.Type.MouseButtonRelease, end, modifiers)

    resized, unchanged = app.maps_service.get_map(document.id).tokens
    assert (resized.cells_w, resized.cells_h) == pytest.approx(size)
    assert (resized.x, resized.y) == pytest.approx(position)
    assert unchanged == other and resized.actor_id == token.actor_id
    assert app.cards_service.get_card(card.id).value("token_cells_w") == 2
    assert stack.index() == index + 1 and stack.undoText() == "Изменить размер объекта"
    assert item.transform_preview is None
    stack.undo()
    assert app.maps_service.get_map(document.id).tokens == (token, other)
    stack.redo()
    assert app.maps_service.get_map(document.id).tokens == (resized, other)


def test_escape_and_return_to_start_discard_preview_but_player_gets_saved_size_under_fog(
    project, tmp_path, qtbot,
):
    app, projects = project
    document, viewer = open_map(app, projects, tmp_path, qtbot)
    card = app.create_card("Сундук", card_type="object")
    token = app.actions.place_card(document.id, card.id, 180, 128)
    other = app.actions.place_card(document.id, card.id, 360, 250)
    character = app.create_card("Страж", card_type="character")
    app.actions.place_card(document.id, character.id, 350, 110)
    fog = QPainterPath()
    fog.addRect(QRectF(220, 0, 280, 400))
    app.maps_service.edit_fog(document.id, fog)
    player = app.maps.open_presentation(document.id)
    qtbot.waitUntil(lambda: player.view._display_ready)
    view = viewer.view
    view.centerOn(token.x, token.y)
    viewport = view.viewport()
    qtbot.mouseClick(viewport, LEFT, pos=view.mapFromScene(QPointF(token.x, token.y)))
    item = view._tokens[0]
    assert item.isSelected() and item.can_transform and not view._tokens[2].can_transform
    assert not player.view._tokens[0].can_transform
    corner = item.sceneBoundingRect().bottomRight()
    end = corner + QPointF(64, 64)
    before = render(player.view)
    stack = app.maps_service.undo_stack(document.id)
    index = stack.index()

    world_mouse(view, QEvent.Type.MouseButtonPress, corner)
    world_mouse(view, QEvent.Type.MouseMove, end)
    assert player.view._tokens[0].token == token and render(player.view) == before
    world_mouse(view, QEvent.Type.MouseMove, corner)
    assert item.transform_preview is None
    world_mouse(view, QEvent.Type.MouseMove, end)
    qtbot.keyClick(view, Qt.Key.Key_Escape)
    world_mouse(view, QEvent.Type.MouseButtonRelease, end)
    assert item.transform_preview is None and item.token == token
    assert stack.index() == index and render(player.view) == before

    world_mouse(view, QEvent.Type.MouseButtonPress, corner)
    world_mouse(view, QEvent.Type.MouseButtonRelease, end)
    resized = app.maps_service.get_map(document.id).tokens[0]
    assert (resized.cells_w, resized.cells_h) == pytest.approx((2, 2))
    assert player.view._tokens[0].token == resized
    assert player.view._tokens[0].transform_preview is None
    after = render(player.view)
    visible = player.view.mapFromScene(QPointF(196, 182))
    hidden = player.view.mapFromScene(QPointF(242, 182))
    assert after.pixelColor(visible).name() == "#713d49"
    assert before.pixelColor(visible) != after.pixelColor(visible)
    assert after.pixelColor(hidden).name() == "#000000"

    assert projects.save_current()
    folder = projects.store.root
    assert projects.create_project(tmp_path / "Empty", preserve_current=False)
    projects.open_project(folder)
    reopened = app.maps_service.get_map(document.id)
    assert reopened.tokens[:2] == (resized, other) and reopened.fog.regions
    assert app.cards_service.get_card(card.id).value("token_cells_w") == 1


def test_external_change_retires_unfinished_object_resize(project, tmp_path, qtbot):
    app, projects = project
    document, viewer = open_map(app, projects, tmp_path, qtbot)
    card = app.create_card("Камень", card_type="object")
    token = app.actions.place_card(document.id, card.id, 180, 130)
    view = viewer.view
    view.select_token(token.id)
    viewport = view.viewport()
    item = view._tokens[0]
    corner = item.sceneBoundingRect().bottomRight()
    start = view.mapFromScene(corner)
    end = view.mapFromScene(corner + QPointF(64, 64))
    stack = app.maps_service.undo_stack(document.id)
    index = stack.index()
    qtbot.mousePress(viewport, LEFT, pos=start)
    mouse_move(view, end)
    assert item.transform_preview is not None
    app.maps_service.move_token(document.id, token.id, 200, 200)
    qtbot.mouseRelease(viewport, LEFT, pos=end)
    current = app.maps_service.get_map(document.id).tokens[0]
    assert (current.x, current.y, current.cells_w, current.cells_h) == (200, 200, None, None)
    assert item.transform_preview is None and stack.index() == index + 1


@pytest.mark.parametrize("modifiers,angle", [(Qt.KeyboardModifier.NoModifier, 47.25), (SHIFT, 45)])
def test_rotate_from_center_and_resize_rotated_token_without_jumping(
    project, tmp_path, qtbot, modifiers, angle,
):
    app, projects = project
    document, viewer = open_map(app, projects, tmp_path, qtbot)
    card = app.create_card("Заслон", card_type="object")
    token = app.actions.place_card(document.id, card.id, 200, 160, cells_w=2, cells_h=1)
    view = viewer.view
    view.select_token(token.id)
    view.scale(1.25, 1.25)
    item = view._tokens[0]
    center = item.scenePos()
    before = app.maps_service.get_map(document.id)
    player = app.maps.open_presentation(document.id)
    qtbot.waitUntil(lambda: player.view._display_ready)
    before_player = render(player.view)
    stack = app.maps_service.undo_stack(document.id)
    index = stack.index()
    handle = rotation_handle(view, item.sceneTransform(), item.boundingRect())
    end = center + QTransform().rotate(47.25).map(handle - center)
    world_mouse(view, QEvent.Type.MouseButtonPress, handle, modifiers)
    world_mouse(view, QEvent.Type.MouseMove, end, modifiers)
    assert item.rotation() == pytest.approx(angle)
    assert item.scenePos() == center and app.maps_service.get_map(document.id) == before
    assert player.view._tokens[0].rotation() == 0 and render(player.view) == before_player
    qtbot.keyClick(view, Qt.Key.Key_Escape)
    world_mouse(view, QEvent.Type.MouseButtonRelease, end, modifiers)
    assert not item.rotation() and stack.index() == index

    world_mouse(view, QEvent.Type.MouseButtonPress, handle, modifiers)
    world_mouse(view, QEvent.Type.MouseButtonRelease, end, modifiers)
    turned = app.maps_service.get_map(document.id).tokens[0]
    assert turned.rotation == pytest.approx(angle) and item.scenePos() == center
    assert player.view._tokens[0].rotation() == turned.rotation
    assert stack.index() == index + 1 and stack.undoText() == "Повернуть объект"

    rect = item.boundingRect()
    outer = item.sceneBoundingRect().topLeft() + QPointF(2, 2)
    inner = item.mapToScene(QPointF(rect.right() - 4, 0))
    assert view.itemAt(view.mapFromScene(outer)) is not item
    assert view.itemAt(view.mapFromScene(inner)) is item
    anchor = item.mapToScene(rect.topLeft())
    handle = item.mapToScene(rect.bottomRight()) + QPointF(2, -1)
    end = handle + QTransform().rotate(angle).map(QPointF(-127.995, -63.9875))
    world_mouse(view, QEvent.Type.MouseButtonPress, handle)
    world_mouse(view, QEvent.Type.MouseMove, handle)
    assert item.transform_preview is None
    world_mouse(view, QEvent.Type.MouseMove, end)
    width, height = item.transform_preview.cells_w, item.transform_preview.cells_h
    assert (width, height) == pytest.approx((0.005 / 64, 0.0125 / 64))
    assert (item.mapToScene(item.boundingRect().topLeft()) - anchor).manhattanLength() < 1e-8
    world_mouse(view, QEvent.Type.MouseButtonRelease, end)
    small = app.maps_service.get_map(document.id).tokens[0]
    assert small.rotation == turned.rotation and (small.cells_w, small.cells_h) == (width, height)
    assert stack.index() == index + 2
    stack.undo()
    assert app.maps_service.get_map(document.id).tokens[0] == turned
    stack.undo()
    assert app.maps_service.get_map(document.id).tokens[0] == token
    stack.redo()
    stack.redo()
    assert app.maps_service.get_map(document.id).tokens[0] == small
    assert projects.save_current()
    folder = projects.store.root
    assert projects.create_project(tmp_path / "Empty", preserve_current=False)
    projects.open_project(folder)
    assert projects.store.root == folder
    reopened = app.maps.open_map(document.id).widget()
    qtbot.waitUntil(lambda: reopened.token_add.isEnabled(), timeout=15000)
    item = reopened.view._tokens[0]
    assert item.token == small and item.rotation() == small.rotation
    assert item.boundingRect().width() == width * reopened.view.grid.cell_size
    assert item.boundingRect().height() == height * reopened.view.grid.cell_size


def test_rotated_token_moves_and_its_swept_footprint_respects_fog(project, tmp_path, qtbot):
    app, projects = project
    app.window.show()
    document, viewer = open_map(app, projects, tmp_path, qtbot)
    card = app.create_card("Плот", card_type="object")
    token = app.actions.place_card(
        document.id, card.id, 180, 145, cells_w=2, cells_h=0.5, rotation=45,
    )
    view = viewer.view
    view.select_token(token.id)
    view.resetTransform()
    view.centerOn(180, 145)
    player = app.maps.open_presentation(document.id)
    qtbot.waitUntil(lambda: player.view._display_ready)
    viewed = player.view._tokens[0]
    assert viewed.rotation() == 45
    outside = QPainterPath()
    outside.addRect(QRectF(126, 192, 3, 3))
    player.view._fog_path = outside
    assert player.view.public_motion_visible(viewed, (180, 145), (180, 145))
    crossing = QPainterPath()
    crossing.addRect(QRectF(240, 185, 3, 3))
    player.view._fog_path = crossing
    assert player.view.public_motion_visible(viewed, (160, 145), (160, 145))
    assert player.view.public_motion_visible(viewed, (240, 145), (240, 145))
    assert not player.view.public_motion_visible(viewed, (160, 145), (240, 145))

    viewport = view.viewport()
    start = view.mapFromScene(QPointF(180, 145))
    end = view.mapFromScene(QPointF(210, 162))
    qtbot.mousePress(viewport, LEFT, pos=start)
    qtbot.mouseMove(viewport, pos=end, delay=20)
    qtbot.mouseRelease(viewport, LEFT, pos=end)
    qtbot.waitUntil(lambda: app.maps_service.get_map(document.id).tokens[0].x != token.x)
    moved = app.maps_service.get_map(document.id).tokens[0]
    assert (moved.x, moved.y) == pytest.approx((210, 162), abs=2)
    assert (moved.cells_w, moved.cells_h, moved.rotation) == (2, 0.5, 45)


def test_non_object_tokens_keep_legacy_geometry_contract(project, tmp_path, qtbot):
    app, projects = project
    document, _ = open_map(app, projects, tmp_path, qtbot)
    card = app.create_card("Предмет", card_type="item")
    token = app.actions.place_card(document.id, card.id, 100, 100)
    for changes in ({"cells_w": 0.7}, {"rotation": 15}, {"cells_h": 101}):
        with pytest.raises(ValueError, match="только объектам"):
            app.maps_service.edit_token(document.id, token.id, **changes)
    assert app.maps_service.get_map(document.id).tokens == (token,)
