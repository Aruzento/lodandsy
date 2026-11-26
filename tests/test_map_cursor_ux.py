import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

from lodandsy.application.fog_geometry import stroke_path
from tests.test_map_presentation import render
from tests.test_map_tokens_grid import open_map

pytest_plugins = ["tests.project_fixture"]

LEFT = Qt.MouseButton.LeftButton
NO_BUTTON = Qt.MouseButton.NoButton
NO_MODIFIER = Qt.KeyboardModifier.NoModifier


def wheel(view, cursor, delta):
    viewport = view.viewport()
    event = QWheelEvent(
        cursor, QPointF(viewport.mapToGlobal(cursor.toPoint())), QPoint(), QPoint(0, delta),
        NO_BUTTON, NO_MODIFIER, Qt.ScrollPhase.NoScrollPhase, False,
    )
    QApplication.sendEvent(viewport, event)


def pointer(view, kind, cursor, button=NO_BUTTON, buttons=NO_BUTTON):
    viewport = view.viewport()
    event = QMouseEvent(
        kind, cursor, QPointF(viewport.mapToGlobal(cursor.toPoint())), button, buttons, NO_MODIFIER,
    )
    QApplication.sendEvent(viewport, event)


@pytest.mark.parametrize("role", ["viewer", "editor"])
def test_wheel_anchors_to_event_position_and_publishes_final_camera(
    project, tmp_path, qtbot, role
):
    app, projects = project
    app.window.resize(970, 650)
    app.window.show()
    document, widget = open_map(app, projects, tmp_path, qtbot)
    if role == "editor":
        widget = app.maps.open_map_editor(document.id).widget()
    view = widget.view
    qtbot.waitUntil(lambda: view._background is not None)
    view.restore_camera({"x": 0.5, "y": 0.5, "zoom": 3})
    cursor = QPointF(view.viewport().width() * 0.28 + 0.3, view.viewport().height() * 0.65)
    frames = []
    view.camera_changed.connect(frames.append)
    player = app.maps.open_presentation(document.id) if role == "viewer" else None
    if player:
        qtbot.waitUntil(lambda: player.view._display_ready)
    for delta in (120, 120, -120, -120):
        scale = view.transform().m11()
        world = view.viewportTransform().inverted()[0].map(cursor)
        frames.clear()
        wheel(view, cursor, delta)
        assert view.transform().m11() == pytest.approx(scale * (1.2 if delta > 0 else 1 / 1.2))
        after = view.viewportTransform().map(world)
        assert abs(after.x() - cursor.x()) <= 0.51
        assert abs(after.y() - cursor.y()) <= 0.51
        if player:
            assert len(frames) == 1
            assert frames[0] == player.view._source_rect
    view.restore_camera({"x": 0.5, "y": 0.5, "zoom": 16})
    unchanged = view.viewportTransform()
    wheel(view, cursor, 120)
    wheel(view, cursor, 0)
    assert view.viewportTransform() == unchanged


@pytest.mark.parametrize("mode", ["hide", "erase"])
def test_fog_brush_outline_tracks_cursor_without_editing_world(
    project, tmp_path, qtbot, mode
):
    app, projects = project
    app.window.show()
    document, widget = open_map(app, projects, tmp_path, qtbot)
    view, tools = widget.view, widget.fog_tools
    player = app.maps.open_presentation(document.id)
    qtbot.waitUntil(lambda: player.view._display_ready)
    view.restore_camera({"x": 0.5, "y": 0.5, "zoom": 2})
    cursor = view.viewportTransform().map(QPointF(240, 195))
    rev = projects.saver.revision
    stack = app.maps_service.undo_stack(document.id)
    index = stack.index()
    pointer(view, QEvent.Type.MouseMove, cursor)
    assert tools.brush_outline() is None
    tools.set_mode(mode)
    outline = tools.brush_outline()
    assert outline == stroke_path(((240, 195),), tools.size.value())
    QApplication.sendEvent(view.viewport(), QEvent(QEvent.Type.Leave))
    baseline = render(view), render(player.view)
    cursor = view.viewportTransform().map(QPointF(240, 195))
    pointer(view, QEvent.Type.MouseMove, cursor)
    assert render(view) != baseline[0]
    assert render(player.view) == baseline[1]

    tools.size.setValue(62)
    assert tools.brush_outline().boundingRect() == QRectF(209, 164, 62, 62)
    pointer(view, QEvent.Type.MouseButtonPress, cursor, LEFT, LEFT)
    moved = cursor + QPointF(24.25, 17.25)
    pointer(view, QEvent.Type.MouseMove, moved, buttons=LEFT)
    assert tools.brush_outline().boundingRect().center() == (
        view.viewportTransform().inverted()[0].map(moved)
    )
    assert tools.points
    wheel(view, moved, 120)
    assert tools.brush_outline().boundingRect().width() == 62
    aligned = view.viewportTransform().map(tools.brush_outline().boundingRect().center())
    assert (aligned - moved).manhattanLength() < 1e-8
    qtbot.keyPress(view, Qt.Key.Key_Space)
    assert tools.brush_outline() is None and not tools.points
    qtbot.keyRelease(view, Qt.Key.Key_Space)
    assert tools.brush_outline() is not None
    QApplication.sendEvent(view.viewport(), QEvent(QEvent.Type.Leave))
    assert tools.brush_outline() is None
    view.restore_camera({"x": 0.5, "y": 0.5, "zoom": 0.4})
    outside_map = view.viewportTransform().map(QPointF(-10, 195))
    assert QRectF(view.viewport().rect()).contains(outside_map)
    pointer(view, QEvent.Type.MouseMove, outside_map)
    assert tools.brush_outline() is None
    assert not app.maps_service.get_map(document.id).fog.regions
    assert stack.index() == index and projects.saver.revision == rev
