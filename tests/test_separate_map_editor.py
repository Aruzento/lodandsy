from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsItem

from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.application.workspace_state import capture_workspace, restore_workspace
from tests.test_map_tokens_grid import open_map

pytest_plugins = ["tests.project_fixture"]


def test_separate_editor_shared_map_independent_camera_and_current_payload(
    project, qtbot, tmp_path
):
    app, project = project
    app.window.show()
    document, viewer = open_map(app, project, tmp_path, qtbot)
    window = app.modules.open_map_editor(document.id)
    editor = window.widget()
    editor.view.set_tool("place")
    qtbot.keyPress(editor.view, Qt.Key.Key_Space)
    assert editor.view.tool == "pan"
    qtbot.keyRelease(editor.view, Qt.Key.Key_Space)
    assert editor.view.tool == "place"
    qtbot.keyClick(editor.view, Qt.Key.Key_Escape)
    assert editor.view.tool == "select"
    assert app.modules.open_map_editor(document.id) is window
    assert (
        viewer.view is not editor.view
        and editor.view.role == "editor"
        and viewer.view.role == "viewer"
    )
    assert not hasattr(viewer, "edit_mode") and not hasattr(document.grid, "snap")
    assert editor.view._background.pyramid is viewer.view._background.pyramid
    layer = app.modules.session.add_layer(document.id, "Decor")
    card = app.create_card("Character", card_type="character")
    token = app.modules.session.add_token(document.id, card.id, 113.25, 137.75)
    app.modules.session.move_token(document.id, token.id, 191.25, 187.75)
    assert app.modules.session.get_map(document.id).tokens[0].x == 191.25
    assert not (editor.view._tokens[0].flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
    app.modules._editor_place(document.id, layer.id, document.asset_id, 100, 100)
    item = app.modules.session.get_map(document.id).objects[0]
    assert item.id in viewer.view._objects and item.id in editor.view._objects
    editor.controls["width"].setValue(180)
    editor.controls["rotation"].setValue(30)
    editor._apply_properties()
    assert app.modules.session.get_map(document.id).objects[0].width == 180
    assert viewer.view._objects[item.id].rotation() == 30
    app.modules.session.edit_layer(document.id, layer.id, visible=False)
    assert not viewer.view._objects[item.id].isVisible()
    app.modules.session.edit_layer(document.id, layer.id, visible=True)
    before = viewer.camera_state()
    editor.view.scale(1.7, 1.7)
    editor.view.centerOn(250, 180)
    assert viewer.camera_state() == before
    app.modules.session.delete_object(document.id, item.id)
    app.modules.session.undo_stack(document.id).undo()
    assert item.id in editor.view._objects
    saved = capture_workspace(app)
    assert "map-editor:" + document.id in saved["documents"]
    app.window_manager.close_window("map-editor:" + document.id)
    restore_workspace(app, saved)
    assert app.window_manager.find_window("map-editor:" + document.id)
    assert project.save_current()
    backup = tmp_path / "backup.lodbackup"
    project.store.backup(backup)
    restored = SQLiteProjectStore.restore(backup, tmp_path / "restored")
    assert restored.load().maps == project.store.load().maps
    restored.close()
    app.modules.session.delete_map(document.id)
    assert not app.window_manager.find_window("map:" + document.id)
    assert not app.window_manager.find_window("map-editor:" + document.id)
