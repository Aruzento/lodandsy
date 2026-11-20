import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter

from tests.test_map_tokens_grid import open_map

pytest_plugins = ["tests.project_fixture"]


def render(view):
    image = QImage(view.viewport().size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.magenta)
    painter = QPainter(image)
    view.viewport().render(painter, QPoint())
    painter.end()
    return image


def test_shared_model_read_only_camera_letterbox_and_lifecycle(project, tmp_path, qtbot):
    app, project = project
    document, viewer = open_map(app, project, tmp_path, qtbot)
    revision = project.saver.revision
    player = app.maps.open_presentation(document.id)
    assert app.maps.open_presentation(document.id) is player
    player.resize(1000, 300)
    qtbot.waitUntil(lambda: player.view._display_ready)
    source = viewer.view.mapToScene(viewer.view.viewport().rect()).boundingRect()
    assert player.view._source_rect == source
    before = app.maps_service.get_map(document.id)
    qtbot.mouseClick(player.view.viewport(), Qt.MouseButton.RightButton, pos=QPoint(40, 40))
    qtbot.keyClick(player.view, Qt.Key.Key_Delete)
    assert app.maps_service.get_map(document.id) == before and project.saver.revision == revision
    image = render(player.view)
    assert image.pixelColor(1, image.height() // 2).name() == "#000000"
    app.window_manager.close_window("map:" + document.id)
    assert document.id not in app.maps.presentations
    assert app.maps_service.get_map(document.id) == before


def test_closing_player_keeps_next_document_native_editor_alive(project, tmp_path, qtbot):
    from PySide6.QtWidgets import QApplication, QLineEdit

    if QApplication.platformName() != "windows":
        pytest.skip("Native Windows activation is exercised by the Windows QPA CI gate")
    app, project = project
    app.window.show()
    document, viewer = open_map(app, project, tmp_path, qtbot)
    player = app.maps.open_presentation(document.id)
    qtbot.waitExposed(player)
    player.close()
    table = app.tables_service.create_table("Next")
    widget = app.tables.open_table(table.id).widget()
    widget.add_row()
    widget.table.edit(widget.model.index(0, 0))
    QApplication.processEvents()
    assert any(e.isVisible() for e in widget.table.findChildren(QLineEdit))


def test_camera_roundtrip_covers_objects_outside_background(qtbot):
    from PySide6.QtCore import QRectF

    from lodandsy.ui.map_widget import MapView

    view = MapView()
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.map_width, view.map_height = 500, 400
    view.scene().setSceneRect(QRectF(-50, -50, 2500, 1500))
    view.show()
    view.restore_camera(dict(x=4, y=2, zoom=1))
    camera = view.camera()
    assert abs(camera["x"] - 4) < 0.02
    assert abs(camera["y"] - 2) < 0.02
