import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QImageIOHandler, QImageWriter, QPalette
from PySide6.QtWidgets import QToolButton

from lodandsy.domain.card import Portrait
from lodandsy.ui.portrait_crop_dialog import PortraitCropDialog
from lodandsy.ui.theme import apply_theme
from tests.test_map_tokens_grid import open_map

pytest_plugins = ["tests.project_fixture"]


@pytest.mark.parametrize("size", [(800, 600), (600, 800), (600, 600)])
@pytest.mark.parametrize("dpr", [1, 1.5, 2])
def test_crop_ten_no_change_cycles_inverse_zoom_and_source_aspect(qtbot, size, dpr):
    image = QImage(*size, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.red)
    image.setDevicePixelRatio(dpr)
    original = (
        0.1,
        0.2,
        0.3,
        0.5,
    )  # Rectangular saved regions remain unchanged until explicit recrop.
    for _ in range(10):
        dialog = PortraitCropDialog(image, original)
        qtbot.addWidget(dialog)
        dialog.resize(680, 500)
        dialog.accept()
        assert dialog.crop() == original
    dialog.canvas.set_zoom(200)
    crop = dialog.crop()
    assert crop[2] * size[0] == pytest.approx(crop[3] * size[1])
    assert min(size) / (crop[2] * size[0]) == pytest.approx(2)
    for _ in range(10):
        reopened = PortraitCropDialog(image, crop)
        qtbot.addWidget(reopened)
        assert reopened.canvas.zoom == pytest.approx(2)
        assert reopened.crop() == crop
        reopened.reject()


def test_card_layout_is_square_stable_after_loading_and_switches(project, qtbot):
    app, _ = project
    card = app.create_card("Карточка", card_type="character")
    editor = app.open_card_editor(card.id).widget()
    editor.resize(850, 760)
    editor.show()
    assert not hasattr(editor, "header_scroll")
    assert editor.hero_layout.itemAt(0).widget() is editor.portrait_panel
    image = QImage(400, 200, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.green)
    panel = editor.portrait_panel
    panel.image_provider = lambda key: image
    panel.set_portrait(Portrait(card.id))
    before = panel.size()
    qtbot.waitUntil(lambda: panel.image.width() == panel.width())
    assert panel.image.height() == panel.height()
    for section in card.sections:
        editor.select_section(section.id)
        panel.refresh_image()
        assert panel.size() == before and before.width() == before.height()
    assert editor.text_edit.mapTo(editor, editor.text_edit.rect().topLeft()).x() == 16
    assert editor.text_edit.maximumWidth() > editor.width()
    assert editor.body.height() > 250


def test_object_catalog_original_geometry_alpha_layers_and_undo(
    project, qtbot, tmp_path, monkeypatch
):
    app, project = project
    document, viewer = open_map(app, project, tmp_path, qtbot)
    image = QImage(400, 200, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    image.setPixelColor(200, 100, QColor("red"))
    source = tmp_path / "Объект.png"
    assert image.save(str(source))
    asset = project.store.import_asset(source)
    project.assets[asset.id] = asset
    original = (project.store.root / asset.path).read_bytes()
    card = app.actions.create_object_card("Объект", asset.id)
    other = app.create_card("Персонаж", card_type="character")
    app.cards_service.update_card(other.id, portrait=Portrait(asset.id))
    app.create_card("Без картинки", card_type="object")
    editor = app.maps.open_map_editor(document.id).widget()
    assert editor.library_model.ids == (card.id,)
    editor.select_library_card(card.id)
    app.cards_service.update_card(card.id, portrait=Portrait(asset.id, (0.25, 0.25, 0.5, 0.5)))
    assert editor.assets.currentIndex().data(Qt.ItemDataRole.UserRole) == card.id
    layers = [app.maps_service.add_layer(document.id, f"Layer {i}") for i in range(3)]
    for layer in layers:
        app.maps._editor_place(document.id, layer.id, card.id, 100, 100)
    placed = app.maps_service.get_map(document.id).objects
    assert all((item.width, item.height, item.asset_id) == (128, 64, asset.id) for item in placed)
    assert editor.layers.item(0).data(Qt.ItemDataRole.UserRole) == layers[-1].id
    editor.layers.setCurrentRow(1)
    selected = editor.active_layer()
    app.maps._editor_layer_action(document.id, "up")
    assert editor.active_layer() == selected and editor.layers.currentRow() == 0
    assert not editor.layer_actions["up"].isEnabled() and editor.layer_actions["down"].isEnabled()
    object_z = {o.layer_id: viewer.view._objects[o.id].zValue() for o in placed}
    assert object_z[selected] > max(z for key, z in object_z.items() if key != selected)
    app.maps_service.undo_stack(document.id).undo()
    assert editor.layers.currentRow() == 1 and editor.active_layer() == selected
    monkeypatch.setattr(app.maps, "_image_filename", lambda: str(source))
    app.maps._editor_import_asset(document.id)
    app.media.wait_import()
    assert len(editor.library_model.ids) == 2
    imported = app.references.info(editor.assets.currentIndex().data(Qt.ItemDataRole.UserRole))
    assert imported.card_type == "object" and imported.image_id == asset.id
    app.actions.delete_entity(card.id)
    assert app.maps_service.get_map(document.id).objects == placed
    assert (project.store.root / asset.path).read_bytes() == original
    assert project.save_current()
    assert project.store.load().maps[0].objects == placed
    for surface in (viewer, editor):
        undo = next(
            b
            for b in surface.findChildren(QToolButton)
            if b.defaultAction() and b.defaultAction().shortcut().toString() == "Ctrl+Z"
        )
        assert undo.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
        assert "Ctrl+Z" in undo.toolTip()


def test_oriented_metadata_matches_decoded_original(project, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    source = tmp_path / "oriented.jpg"
    writer = QImageWriter(str(source), b"jpeg")
    writer.setTransformation(QImageIOHandler.Transformation.TransformationRotate90)
    image = QImage(400, 200, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.red)
    assert writer.write(image)
    asset = project.store.import_asset(source)
    project.assets[asset.id] = asset
    from lodandsy.application.media_service import read_card_image

    decoded = read_card_image(project.store.root / asset.path)
    assert app.maps.asset_size(asset.id) == decoded.size()


def test_neutral_palette_and_widget_surfaces(qapp):
    palette, sheet, font = qapp.palette(), qapp.styleSheet(), qapp.font()
    try:
        apply_theme(qapp)
        for role in (
            QPalette.ColorRole.Window,
            QPalette.ColorRole.Base,
            QPalette.ColorRole.Button,
            QPalette.ColorRole.Highlight,
            QPalette.ColorRole.Link,
        ):
            color = qapp.palette().color(role)
            assert abs(color.red() - color.blue()) <= 10
        assert "#304e75" not in qapp.styleSheet() and "#ceb075" not in qapp.styleSheet()
        assert "font-size:32px" in qapp.styleSheet()
    finally:
        qapp.setPalette(palette)
        qapp.setStyleSheet(sheet)
        qapp.setFont(font)
