from dataclasses import replace
from uuid import uuid4

import pytest
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainterPath

from lodandsy.domain.map_document import MapGrid, MapShape
from tests.project_fixture import map_services

pytest_plugins = ["tests.project_fixture"]


@pytest.mark.parametrize(
    "kind,points",
    [
        ("circle", ((64, 0),)),
        ("cone", ((64, 0),)),
        ("triangle", ((0, 0), (10, 0), (10, 10))),
        ("rectangle", ((0, 0), (10, 0), (10, 10), (0, 10))),
        ("quadrilateral", ((0, 0), (20, 0), (10, 10), (0, 20))),
        ("polygon", ((0, 0), (10, 0), (10, 10), (0, 10))),
    ],
)
def test_shape_undo_does_not_replace_independent_fog(qapp, kind, points):
    service, *_ = map_services()
    document = service.create_map("Map", str(uuid4()))
    value = MapShape(kind, points)
    service.put_vector(document.id, value)
    assert service.get_map(document.id).shapes == (value,)
    path = QPainterPath()
    path.addRect(QRectF(0, 0, 100, 100))
    # Independent canonical change outside map history must survive shape Undo.
    from lodandsy.application.fog_geometry import apply_fog

    current = service.get_map(document.id)
    service._put_map(replace(current, fog=apply_fog(current.fog, path)))
    fog = service.get_map(document.id).fog
    service.undo_stack(document.id).undo()
    assert not service.get_map(document.id).shapes
    assert service.get_map(document.id).fog == fog
    service.undo_stack(document.id).redo()
    assert service.get_map(document.id).shapes == (value,)


@pytest.mark.parametrize(
    "points",
    [((0, 0), (10, 10), (0, 10), (10, 0)), ((0, 0), (0, 0), (10, 10)), ((0, 0), (1, 0), (2, 0))],
)
def test_invalid_polygon_rejected(points):
    with pytest.raises(ValueError):
        MapShape("polygon", points)


@pytest.mark.parametrize("dpr", [1, 1.25, 1.5, 2])
def test_public_shape_is_above_fog_without_revealing_background(qtbot, dpr):
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QColor, QImage, QPainter

    from lodandsy.ui.map_widget import MapView

    view = MapView("player")
    view.grid = MapGrid(feet_per_cell=5)
    qtbot.addWidget(view)
    view.resize(500, 400)
    view.setSceneRect(QRectF(0, 0, 400, 300))
    view._source_rect = QRectF(0, 0, 400, 300)
    view.scene().setBackgroundBrush(QColor("#ff0000"))
    path = QPainterPath()
    path.addRect(QRectF(0, 0, 400, 300))
    view._fog_path = path
    view.vector_shapes = (
        MapShape("circle", ((50, 0),), x=200, y=150, color="#00ff00", opacity=0.5),
    )
    view.show()
    qtbot.waitExposed(view)
    view._display_ready = True
    image = QImage(
        int(view.viewport().width() * dpr),
        int(view.viewport().height() * dpr),
        QImage.Format.Format_ARGB32,
    )
    image.setDevicePixelRatio(dpr)
    painter = QPainter(image)
    view.viewport().render(painter, QPoint())
    painter.end()
    for point, inside in [(QPointF(200, 150), True), (QPointF(50, 50), False)]:
        pixel = view.viewportTransform().map(point)
        color = image.pixelColor(int(pixel.x() * dpr), int(pixel.y() * dpr))
        assert color.red() == 0 and color.blue() == 0
        assert 120 <= color.green() <= 135 if inside else color.green() == 0


def test_shape_native_create_properties_and_cancel(project, tmp_path, qtbot):
    from PySide6.QtCore import QPointF, Qt

    from tests.test_map_tokens_grid import open_map

    app, session = project
    document, viewer = open_map(app, session, tmp_path, qtbot)
    tools = viewer.vector_tools
    tools.show()
    tools.set_mode("circle")
    start = viewer.view.mapFromScene(QPointF(200, 150))
    end = viewer.view.mapFromScene(QPointF(264, 150))
    qtbot.mousePress(viewer.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(viewer.view.viewport(), pos=end)
    assert not app.maps_service.get_map(document.id).shapes
    qtbot.mouseRelease(viewer.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    value = app.maps_service.get_map(document.id).shapes[0]
    assert value.kind == "circle"
    tools.name.setText("Область")
    tools.apply_properties()
    assert app.maps_service.get_map(document.id).shapes[0].name == "Область"
    qtbot.mousePress(viewer.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(viewer.view.viewport(), pos=end)
    qtbot.keyClick(viewer.view, Qt.Key.Key_Escape)
    qtbot.mouseRelease(viewer.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert len(app.maps_service.get_map(document.id).shapes) == 1


def test_portal_retarget_and_portrait_lifecycle(project, tmp_path, qtbot):
    from lodandsy.domain.map_document import MapPortal
    from tests.test_map_tokens_grid import open_map

    app, session = project
    first, viewer = open_map(app, session, tmp_path, qtbot)
    second = app.maps_service.create_map("Вторая", first.asset_id)
    portal = MapPortal(second.id, 100, 100)
    app.maps_service.put_vector(first.id, portal)
    app.maps._portal_open(first.id, portal.id)
    assert not app.maps.presentations
    player = app.maps.open_presentation(first.id)
    qtbot.waitUntil(lambda: player.view._display_ready)
    app.maps._portal_open(first.id, portal.id)
    assert app.maps.presentations[second.id] is player
    qtbot.waitUntil(lambda: player.view._display_ready)
    card = app.create_card("Portrait")
    app.cards_service.update_card_fields(card.id, {"token_image": first.asset_id})
    token = app.maps_service.add_token(second.id, card.id, 200, 150)
    app.maps._token_action(second.id, token.id, "portrait")
    assert len(app.maps._portrait_views) == 2
    app.maps._portrait_views[1].dismissed.emit()
    assert app.maps._portrait is None and not app.maps._portrait_views
    app.maps._token_action(second.id, token.id, "portrait")
    app.maps_service.delete_token(second.id, token.id)
    assert app.maps._portrait is None


@pytest.mark.parametrize("shift", [False, True])
@pytest.mark.parametrize("alt", [False, True])
def test_resize_after_rotation_preserves_anchor(qtbot, shift, alt):
    from PySide6.QtCore import QPointF, Qt

    from lodandsy.ui.map_vectors import VectorTools, local_path, transform
    from lodandsy.ui.map_widget import MapView

    view = MapView()
    qtbot.addWidget(view)
    tools = VectorTools(view)
    qtbot.addWidget(tools)
    value = MapShape(
        "rectangle", ((-50, -25), (50, -25), (50, 25), (-50, 25)), x=100, y=200, rotation=37
    )
    view.vector_shapes = (value,)
    tools.select(value)
    rect = local_path(value).boundingRect()
    anchor = rect.center() if shift else rect.topLeft()
    before = transform(value).map(anchor)
    tools.gesture = ("resize", value, QPointF(), 0)
    modifiers = Qt.KeyboardModifier.NoModifier
    if shift:
        modifiers |= Qt.KeyboardModifier.ShiftModifier
    if alt:
        modifiers |= Qt.KeyboardModifier.AltModifier
    tools.update_gesture(transform(value).map(QPointF(100, 75)), modifiers)
    candidate = tools.preview
    assert candidate is not None
    assert transform(candidate).map(anchor) == before
    candidate_rect = local_path(candidate).boundingRect()
    if alt:
        assert candidate_rect.width() / candidate_rect.height() == pytest.approx(2)


def test_vectors_backup_and_previous_map7_read(project, tmp_path):
    import hashlib
    import json
    import sqlite3

    from lodandsy.application.sqlite_project_store import SQLiteProjectStore
    from lodandsy.domain.map_document import MapPortal
    from tests.test_actor_storage import world

    app, session, card, actor, document = world(project, tmp_path)
    target = app.maps_service.create_map("Target", document.asset_id)
    shape = MapShape("circle", ((64, 0),), x=100, y=100)
    portal = MapPortal(target.id, 40, 50)
    app.maps_service.put_vector(document.id, shape)
    app.maps_service.put_vector(document.id, portal)
    assert session.save_current()
    snapshot = session.store.load()
    saved = next(v for v in snapshot.maps if v.id == document.id)
    assert saved.shapes == (shape,) and saved.portals == (portal,)
    backup = tmp_path / "m5.lodbackup"
    session.store.backup(backup)
    restored = SQLiteProjectStore.restore(backup, tmp_path / "restore")
    assert next(v for v in restored.load().maps if v.id == document.id) == saved
    restored.close()
    with sqlite3.connect(session.store.path) as connection:
        for key, raw in connection.execute("SELECT id,objects FROM map_document").fetchall():
            connection.execute(
                "UPDATE map_document SET payload_version=7,objects=? WHERE id=?",
                (json.dumps(json.loads(raw)["objects"]), key),
            )
    before = hashlib.sha256(session.store.path.read_bytes()).hexdigest()
    previous = session.store.load()
    assert all(not v.shapes and not v.portals for v in previous.maps)
    assert next(v for v in previous.cards if v.id == card.id).actors[0].id == actor.id
    assert hashlib.sha256(session.store.path.read_bytes()).hexdigest() == before


def test_hidden_portrait_requires_confirmation_and_cancel_is_noop(
    project, tmp_path, qtbot, monkeypatch
):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainterPath
    from PySide6.QtWidgets import QMessageBox

    from tests.test_map_tokens_grid import open_map

    app, session = project
    document, viewer = open_map(app, session, tmp_path, qtbot)
    card = app.create_card("Hidden")
    app.cards_service.update_card_fields(card.id, {"token_image": document.asset_id})
    token = app.maps_service.add_token(document.id, card.id, 200, 150)
    fog = QPainterPath()
    fog.addRect(QRectF(0, 0, 800, 600))
    app.maps_service.edit_fog(document.id, fog)
    before = session.saver.revision
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    app.maps._token_action(document.id, token.id, "portrait")
    assert app.maps._portrait is None and session.saver.revision == before
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    app.maps._token_action(document.id, token.id, "portrait")
    assert len(app.maps._portrait_views) == 1 and not app.maps.presentations
    qtbot.keyClick(app.maps._portrait_views[0], Qt.Key.Key_Escape)
    assert app.maps._portrait is None and session.saver.revision == before


def test_portal_soft_reference_self_and_wrong_kind_guards(project, tmp_path, qtbot):
    from lodandsy.domain.map_document import MapPortal
    from tests.test_map_tokens_grid import open_map

    app, session = project
    document, viewer = open_map(app, session, tmp_path, qtbot)
    before = session.saver.revision
    with pytest.raises(ValueError):
        app.maps_service.put_vector(document.id, MapPortal(document.id, 100, 100))
    card = app.create_card("Not map")
    with pytest.raises(ValueError):
        app.maps_service.put_vector(document.id, MapPortal(card.id, 100, 100))
    portal = MapPortal(str(uuid4()), 100, 100)
    app.maps_service.put_vector(document.id, portal)
    assert app.maps_service.get_map(document.id).portals == (portal,)
    assert session.saver.revision > before


def test_map_vector_snapshot_failure_rolls_back_all_rows(project, tmp_path):
    import sqlite3

    from lodandsy.application.sqlite_project_store import ProjectError
    from tests.test_actor_storage import world

    app, session, card, actor, document = world(project, tmp_path)
    target = app.maps_service.create_map("Second", document.asset_id)
    assert session.save_current()
    before = session.store.load()
    first = next(v for v in before.maps if v.id == document.id)
    second = next(v for v in before.maps if v.id == target.id)
    changed = replace(first, shapes=(MapShape("circle", ((64, 0),), x=100, y=100),))
    changed_second = replace(second, shapes=(MapShape("circle", ((32, 0),), x=70, y=70),))
    candidate = replace(
        before,
        revision=before.revision + 1,
        maps=(changed, changed_second),
    )
    with sqlite3.connect(session.store.path) as connection:
        connection.execute(
            "CREATE TRIGGER m5_fail BEFORE INSERT ON map_document WHEN NEW.id='"
            + target.id
            + "' BEGIN SELECT RAISE(ABORT,'m5 fault'); END"
        )
    with pytest.raises(ProjectError, match="m5 fault"):
        session.store.save(candidate)
    assert session.store.load() == before


def test_private_drag_data_not_published_and_fog_revalidates(project, tmp_path, qtbot):
    from tests.test_map_tokens_grid import open_map

    app, session = project
    document, viewer = open_map(app, session, tmp_path, qtbot)
    card = app.create_card("Mover")
    token = app.maps_service.add_token(document.id, card.id, 200, 150)
    player = app.maps.open_presentation(document.id)
    qtbot.waitUntil(lambda: player.view._display_ready)
    value = (token.id, (200, 150), (450, 150))
    app.maps._measurement(document.id, value, "grid")
    assert player.view.measurement == value
    path = QPainterPath()
    path.addRect(QRectF(300, 100, 50, 100))
    app.maps_service.edit_fog(document.id, path)
    assert player.view.measurement is None
    public = next(i for i in player.view._tokens if i.token.id == token.id)
    app.maps._transient(document.id, "token", token.id, 450, 150, viewer.view)
    assert (public.x(), public.y()) == (200, 150)
    app.maps._measurement(document.id, None, "grid")
    assert player.view.measurement is None and public.isVisible()


def test_polygon_cursor_restored_when_tools_reopen(qtbot):
    from PySide6.QtCore import Qt

    from lodandsy.ui.map_vectors import VectorTools
    from lodandsy.ui.map_widget import MapView

    view = MapView()
    qtbot.addWidget(view)
    tools = VectorTools(view)
    qtbot.addWidget(tools)
    tools.set_mode("polygon")
    tools.show()
    assert view.viewport().cursor().shape() == Qt.CursorShape.CrossCursor
    view.tool_state.activate("select")
    assert view.viewport().cursor().shape() != Qt.CursorShape.CrossCursor
    tools.set_mode("polygon")
    assert view.viewport().cursor().shape() == Qt.CursorShape.CrossCursor


def test_portrait_source_change_during_confirmation_is_rejected(
    project, tmp_path, qtbot, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox

    from tests.test_map_tokens_grid import open_map

    app, session = project
    document, viewer = open_map(app, session, tmp_path, qtbot)
    card = app.create_card("Changing source")
    app.cards_service.update_card_fields(card.id, {"token_image": document.asset_id})
    token = app.maps_service.add_token(document.id, card.id, 200, 150)
    path = QPainterPath()
    path.addRect(QRectF(0, 0, 800, 600))
    app.maps_service.edit_fog(document.id, path)

    def confirm(*args):
        app.cards_service.update_card_fields(card.id, {"token_image": None})
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", confirm)
    monkeypatch.setattr(app.maps, "_error", lambda message: None)
    app.maps._token_action(document.id, token.id, "portrait")
    assert app.maps._portrait is None


@pytest.mark.parametrize("bad", [None, 0, 1, "false", [], {}])
def test_portal_label_visibility_is_strict_boolean(bad):
    from lodandsy.domain.map_document import MapPortal

    with pytest.raises(ValueError, match="видимость"):
        MapPortal(str(uuid4()), 1, 2, hide_label=bad)


def test_map9_portal_reopen_backup_and_map8_read_without_rewrite(project, tmp_path):
    import hashlib
    import json
    import sqlite3

    from lodandsy.application.sqlite_project_store import SQLiteProjectStore
    from lodandsy.domain.map_document import MapPortal
    from tests.test_actor_storage import world

    app, session, card, actor, document = world(project, tmp_path)
    target = app.maps_service.create_map("Цель", document.asset_id)
    portal = MapPortal(target.id, 40, 50, "Имя", hide_label=True)
    app.maps_service.put_vector(document.id, portal)
    assert session.save_current()
    saved = next(v for v in session.store.load().maps if v.id == document.id)
    assert saved.portals == (portal,)
    with sqlite3.connect(session.store.path) as connection:
        version, raw = connection.execute(
            "SELECT payload_version,objects FROM map_document WHERE id=?", (document.id,)
        ).fetchone()
        assert version == 9 and json.loads(raw)["portals"][0]["hide_label"] is True
    backup = tmp_path / "map9.lodbackup"
    session.store.backup(backup)
    restored = SQLiteProjectStore.restore(backup, tmp_path / "map9-restored")
    assert next(v for v in restored.load().maps if v.id == document.id) == saved
    restored.close()
    with sqlite3.connect(session.store.path) as connection:
        raw = json.loads(raw)
        del raw["portals"][0]["hide_label"]
        grid = json.loads(
            connection.execute(
                "SELECT grid FROM map_document WHERE id=?", (document.id,)
            ).fetchone()[0]
        )
        grid.pop("feet_per_cell", None)
        connection.execute(
            "UPDATE map_document SET payload_version=8,objects=?,grid=? WHERE id=?",
            (json.dumps(raw), json.dumps(grid), document.id),
        )
    digest = hashlib.sha256(session.store.path.read_bytes()).digest()
    previous = session.store.load()
    old = next(v for v in previous.maps if v.id == document.id)
    assert old.portals == (replace(portal, hide_label=False),)
    assert old.grid.feet_per_cell is None
    assert next(v for v in previous.cards if v.id == card.id).actors[0].id == actor.id
    assert hashlib.sha256(session.store.path.read_bytes()).digest() == digest


def test_portal_hidden_label_changes_only_caption_pixels(qtbot):
    from PySide6.QtCore import QPointF

    from lodandsy.domain.map_document import MapPortal
    from lodandsy.ui.map_widget import MapView

    view = MapView()
    qtbot.addWidget(view)
    view.resize(500, 300)
    view.setSceneRect(QRectF(0, 0, 500, 300))
    portal = MapPortal(str(uuid4()), 100, 100, "Название портала")
    view.vector_portals = (portal,)
    view.show()
    qtbot.waitExposed(view)
    visible = view.viewport().grab().toImage()
    view.vector_portals = (replace(portal, hide_label=True),)
    hidden = view.viewport().grab().toImage()
    center = view.mapFromScene(QPointF(100, 100))
    assert visible.copy(center.x() - 12, center.y() - 12, 25, 25) == hidden.copy(
        center.x() - 12, center.y() - 12, 25, 25
    )
    assert visible != hidden
    view.role = "player"
    without = view.viewport().grab().toImage()
    view.vector_portals = (portal,)
    assert view.viewport().grab().toImage() == without
