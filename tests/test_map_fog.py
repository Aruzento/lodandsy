import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath

from lodandsy.application.fog_geometry import (
    apply_fog,
    polygon_path,
    region_path,
    state_path,
    stroke_path,
)
from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.domain.map_fog import FogRegion, FogState
from lodandsy.ui.map_widget import MapView
from tests.test_map_presentation import render
from tests.test_map_tokens_grid import open_map

pytest_plugins = ["tests.project_fixture"]


def rectangle(x=0, y=0, w=100, h=100):
    path = QPainterPath()
    path.addRect(x, y, w, h)
    return path


def test_erase_holes_splits_overlap_and_stable_region_ids():
    state = apply_fog(FogState(), rectangle())
    state = apply_fog(state, rectangle(20, 20))
    ids = tuple(r.id for r in state.regions)
    hole = apply_fog(state, rectangle(40, 40, 20, 20), erase=True)
    assert tuple(r.id for r in hole.regions) == ids
    assert all(not region_path(r).contains(QPointF(50, 50)) for r in hole.regions)
    assert all(region_path(r).contains(QPointF(30, 30)) for r in hole.regions)
    split = apply_fog(state, rectangle(45, -10, 10, 200), erase=True)
    assert all(len(r.rings) == 2 for r in split.regions)
    assert apply_fog(state, rectangle(-10, -10, 1000, 1000), erase=True) == FogState()


def test_render_union_never_cancels_overlaps_or_fills_an_uncovered_hole():
    state = apply_fog(FogState(), rectangle())
    state = apply_fog(state, rectangle(20, 20))
    state = apply_fog(state, rectangle(40, 40, 20, 20), erase=True)
    state = apply_fog(state, rectangle(50, 50, 10, 10))
    path = state_path(state)
    assert path.contains(QPointF(30, 30))  # overlap remains hidden
    assert not path.contains(QPointF(45, 45))  # hole in both regions
    assert path.contains(QPointF(55, 55))  # one region covers the others' holes
    reversed_state = FogState(
        tuple(
            FogRegion(tuple(tuple(reversed(r)) for r in region.rings)) for region in state.regions
        )
    )
    reverse = state_path(reversed_state)
    for x in range(-5, 130, 3):
        for y in range(-5, 130, 3):
            point = QPointF(x + 0.2, y + 0.2)
            expected = any(region_path(r).contains(point) for r in state.regions)
            assert path.contains(point) == expected == reverse.contains(point)


def test_numeric_intersecting_rings_cannot_cancel_another_region():
    bow = FogRegion((((0, 0), (100, 100), (0, 100), (50, 0)),))
    overlap = FogRegion(
        (((10, 10), (90, 10), (90, 90), (10, 90)), ((40, 40), (120, 40), (120, 120), (40, 120)))
    )
    state = FogState((bow, overlap))
    compiled = state_path(state)
    for x in range(-5, 130, 3):
        for y in range(-5, 130, 3):
            point = QPointF(x + 0.2, y + 0.2)
            expected = any(region_path(r).contains(point) for r in state.regions)
            assert compiled.contains(point) == expected


@pytest.mark.parametrize(
    "points",
    [((0, 0), (10, 10), (0, 10), (10, 0)), ((0, 0), (1, 0), (2, 0)), ((0, 0), (0, 0), (5, 5))],
)
def test_invalid_polygons_rejected(points):
    with pytest.raises(ValueError):
        polygon_path(points)


def test_geometry_budget_numeric_and_brush_endcaps():
    with pytest.raises(ValueError):
        stroke_path([(0, 0)] * 513, 10)
    with pytest.raises(ValueError):
        stroke_path([(float("nan"), 0)], 10)
    with pytest.raises(ValueError):
        FogRegion((((0, 0), (1, 0), (2, 0)),))
    path = stroke_path([(0, 0), (100, 0)], 20)
    assert path.contains(QPointF(-5, 0)) and path.contains(QPointF(105, 0))


def test_fog_overlay_pixels_undo_backup_reopen_and_transient(project, tmp_path, qtbot):
    app, project = project
    app.window.show()
    document, viewer = open_map(app, project, tmp_path, qtbot)
    card = app.create_card("Token")
    token = app.maps_service.add_token(document.id, card.id, 250, 200)
    layer = document.layers[0]
    app.maps_service.add_object(document.id, layer.id, document.asset_id, 200, 150, 100, 100)
    app.maps_service.edit_fog(document.id, rectangle(150, 100, 200, 200))
    player = app.maps.open_presentation(document.id)
    qtbot.waitUntil(lambda: player.view._display_ready)
    point = player.view.mapFromScene(QPointF(250, 200))
    image = render(player.view)
    assert image.pixelColor(point).name() == "#000000"
    gm_point = viewer.view.mapFromScene(QPointF(250, 200))
    assert render(viewer.view).pixelColor(gm_point).name() != "#000000"
    app.maps_service.edit_fog(document.id, rectangle(200, 150, 50, 100), erase=True)
    partial = render(player.view)
    left = player.view.mapFromScene(QPointF(230, 200))
    right = player.view.mapFromScene(QPointF(270, 200))
    assert partial.pixelColor(left).name() != "#000000"
    assert partial.pixelColor(right).name() == "#000000"
    app.maps_service.undo_stack(document.id).undo()
    assert player.view._fog_state is app.maps_service.get_map(document.id).fog
    assert player.view._fog_path is viewer.view._fog_path
    revision = project.saver.revision
    app.maps._transient(document.id, "token", token.id, 260, 210, viewer.view)
    # M5 withholds hidden transient coordinates; canonical token stays at its origin.
    assert player.view._tokens[0].pos() == QPointF(250, 200)
    assert project.saver.revision == revision
    assert render(player.view).pixelColor(point).name() == "#000000"
    app.maps_service.edit_fog(document.id, rectangle(225, 175, 50, 50), erase=True)
    assert render(player.view).pixelColor(point).name() != "#000000"
    app.maps_service.undo_stack(document.id).undo()
    assert render(player.view).pixelColor(point).name() == "#000000"
    expected = app.maps_service.get_map(document.id)
    assert project.save_current()
    backup = tmp_path / "backup.lodbackup"
    project.store.backup(backup)
    restored = SQLiteProjectStore.restore(backup, tmp_path / "Restored")
    assert restored.load().maps == (expected,)
    restored.close()
    project.open_project(tmp_path / "Restored")
    assert not app.maps.presentations
    assert app.maps_service.get_map(document.id).fog == expected.fog


def test_player_first_frame_is_fail_closed(qtbot):
    view = MapView("player")
    qtbot.addWidget(view)
    view.resize(300, 200)
    view.scene().addRect(QRectF(-10000, -10000, 20000, 20000), brush=Qt.GlobalColor.red)
    view.show()
    assert render(view).pixelColor(150, 100).name() == "#000000"


@pytest.mark.parametrize("dpr", [1, 1.5, 2])
def test_player_opaque_edges_at_device_pixel_ratios(project, tmp_path, qtbot, dpr):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage, QPainter

    app, project = project
    document, viewer = open_map(app, project, tmp_path, qtbot)
    app.maps_service.edit_fog(document.id, rectangle(100, 100, 200, 200))
    player = app.maps.open_presentation(document.id)
    player.resize(700, 500)
    qtbot.waitUntil(lambda: player.view._display_ready)
    view = player.view
    image = QImage(
        int(view.viewport().width() * dpr),
        int(view.viewport().height() * dpr),
        QImage.Format.Format_ARGB32,
    )
    image.setDevicePixelRatio(dpr)
    image.fill(Qt.GlobalColor.magenta)
    painter = QPainter(image)
    view.viewport().render(painter, QPoint())
    painter.end()
    for point in [
        QPointF(100.01, 200),
        QPointF(299.99, 200),
        QPointF(200, 100.01),
        QPointF(200, 299.99),
        QPointF(200, 200),
    ]:
        # Preserve fractions until conversion to the target image's physical pixels.
        # mapFromScene returns QPoint: rounding first can sample outside the fog at DPR>1.
        pixel = view.viewportTransform().map(point)
        color = image.pixelColor(int(pixel.x() * dpr), int(pixel.y() * dpr))
        assert color.name() == "#000000" and color.alpha() == 255


def test_player_fog_at_fractional_viewport_transform(qtbot):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage, QPainter, QTransform

    view = MapView("player")
    qtbot.addWidget(view)
    view.resize(700, 500)
    view._source_rect = QRectF(0, 0, 500, 400)
    view.setSceneRect(view._source_rect)
    view.scene().setBackgroundBrush(Qt.GlobalColor.darkCyan)
    view._fog_path = rectangle(100, 100, 200, 200)
    view.show()
    qtbot.waitExposed(view)
    view.setTransform(QTransform.fromScale(72 / 103, 72 / 103))
    # Exercise foreground rendering directly, independent of media/worker readiness.
    view._display_ready = True
    image = QImage(
        view.viewport().width() * 2, view.viewport().height() * 2, QImage.Format.Format_ARGB32
    )
    image.setDevicePixelRatio(2)
    painter = QPainter(image)
    view.viewport().render(painter, QPoint())
    painter.end()
    for point, expected in [(QPointF(299.99, 200), "#000000"), (QPointF(320, 200), "#008080")]:
        pixel = view.viewportTransform().map(point)
        color = image.pixelColor(int(pixel.x() * 2), int(pixel.y() * 2))
        assert color.name() == expected and color.alpha() == 255


def test_native_gesture_commit_escape_panel_and_selection(project, tmp_path, qtbot):
    app, project = project
    app.window.show()
    document, viewer = open_map(app, project, tmp_path, qtbot)
    tools = viewer.fog_tools
    tools.set_mode("hide")
    view = viewer.view
    point = view.mapFromScene(QPointF(250, 200))
    before = project.saver.revision
    qtbot.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
    assert not app.maps_service.get_map(document.id).fog.regions
    qtbot.keyClick(view, Qt.Key.Key_Escape)
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
    assert project.saver.revision == before
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
    state = app.maps_service.get_map(document.id).fog
    assert len(state.regions) == 1 and project.saver.revision == before + 1
    viewer.tool_state.activate("select")
    assert app.maps_service.get_map(document.id).fog == state
    tools.show()
    tools.set_mode("select")
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
    assert tools.selected == state.regions[0].id
    qtbot.keyClick(view, Qt.Key.Key_Delete)
    assert not app.maps_service.get_map(document.id).fog.regions
    app.maps_service.undo_stack(document.id).undo()
    assert app.maps_service.get_map(document.id).fog == state


@pytest.mark.parametrize("zoom", [0.25, 1, 4])
def test_polygon_screen_snap_nodes_commit_undo(project, tmp_path, qtbot, zoom):
    app, session = project
    app.window.show()
    document, viewer = open_map(app, session, tmp_path, qtbot)
    tools, view = viewer.fog_tools, viewer.view
    tools.show()
    tools.set_mode("polygon")
    view.scale(zoom, zoom)
    points = [(200, 150), (300, 150), (300, 250)]
    tools.points = points.copy()
    first = QPointF(*points[0])
    near = view.mapToScene((view.mapFromScene(first) + QPoint(6, 0)))
    assert tools._snaps(near)
    tools._preview(near)
    assert view._fog_snap and view._fog_vertices == tuple(points)
    assert view._fog_preview.currentPosition() == first
    revision = session.saver.revision
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=view.mapFromScene(near))
    assert session.saver.revision == revision + 1
    assert len(app.maps_service.get_map(document.id).fog.regions) == 1
    assert not tools.points and not view._fog_vertices
    app.maps_service.undo_stack(document.id).undo()
    assert not app.maps_service.get_map(document.id).fog.regions
    app.maps_service.undo_stack(document.id).redo()
    assert app.maps_service.get_map(document.id).fog.regions
    viewer.tool_state.activate("select")
    assert view.viewport().cursor().shape() != Qt.CursorShape.CrossCursor
