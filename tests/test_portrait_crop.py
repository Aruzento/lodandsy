from dataclasses import replace

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from lodandsy.application.workspace_state import capture_workspace, restore_workspace
from lodandsy.domain.card import Portrait
from lodandsy.domain.map_document import TokenInstance, resolve_token
from lodandsy.ui.portrait_crop_dialog import PortraitCropDialog

pytest_plugins = ["tests.project_fixture"]


def test_crop_apply_cancel_reset_and_shared_token_presentation(project, qtbot, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Character", card_type="character")
    image = QImage(800, 600, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.red)
    source = tmp_path / "photo.png"
    image.save(str(source))
    asset = project.store.import_asset(source)
    project.assets[asset.id] = asset
    original = source.read_bytes()
    app.cards_service.update_card(card.id, portrait=Portrait(asset.id))
    editor = app.open_card_editor(card.id).widget()
    panel = editor.portrait_panel
    qtbot.waitUntil(lambda: panel._image is not None and not panel._image.isNull())

    def cancel():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, PortraitCropDialog)
        dialog.zoom.setValue(250)
        dialog.reject()

    QTimer.singleShot(0, cancel)
    panel.edit_crop()
    assert app.cards.get(card.id).portrait.crop == (0.0, 0.0, 1.0, 1.0)

    def apply():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, PortraitCropDialog)
        dialog.zoom.setValue(200)
        dialog.canvas.center += QPointF(20, 0)
        dialog.accept()

    QTimer.singleShot(0, apply)
    panel.edit_crop()
    crop = app.cards.get(card.id).portrait.crop
    assert crop != (0.0, 0.0, 1.0, 1.0) and crop[0] + crop[2] <= 1.00001
    token = TokenInstance(card.id, 10, 20)
    assert resolve_token(token, app.cards.get(card.id)).crop == crop
    assert resolve_token(replace(token, image_override=asset.id), app.cards.get(card.id)).crop == (
        0.0,
        0.0,
        1.0,
        1.0,
    )
    assert source.read_bytes() == original and len(project.assets) == 1
    assert project.save_current() and project.store.load().cards[0].portrait.crop == crop
    dialog = PortraitCropDialog(image, crop)
    qtbot.addWidget(dialog)
    dialog.canvas.reset()
    x, y, w, h = dialog.crop()
    assert 0 <= x < 1 and 0 <= y < 1 and w > 0 and h > 0


def test_native_sidebars_remember_width_after_collapse_and_restore(project, qtbot, tmp_path):
    app, project = project
    app.window.resize(1500, 1000)
    app.window.show()
    project.create_project(tmp_path / "world")
    card = app.create_card("Card")
    app.open_card_editor(card.id)
    app.window.resizeDocks(
        [app.window.tree_host, app.window.inspector_host], [280, 350], Qt.Orientation.Horizontal
    )
    qtbot.wait(30)
    before = app.window.panel_widths()
    app.window.left_rail.tree_action.setChecked(False)
    app.window.left_rail.tree_action.setChecked(True)
    qtbot.wait(30)
    assert abs(app.window.tree_host.width() - before["tree"]) <= 8
    saved = capture_workspace(app)
    app.window.resizeDocks([app.window.tree_host], [200], Qt.Orientation.Horizontal)
    restore_workspace(app, saved)
    assert abs(app.window.tree_host.width() - before["tree"]) <= 8
