from uuid import uuid4

import pytest

from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from tests.project_fixture import map_services
from tests.test_map_tokens_grid import open_map

pytest_plugins = ["tests.project_fixture"]


def test_layer_objects_undo_and_validation(qapp):
    session, actions, tables, cards_service = map_services()
    document = session.create_map("Map", str(uuid4()))
    first = session.add_layer(document.id, "Terrain")
    second = session.add_layer(document.id, "Houses")
    item = session.add_object(document.id, first.id, str(uuid4()), 10, 20, 200, 100)
    session.edit_object(document.id, item.id, width=300, rotation=45, x=30)
    session.undo_stack(document.id).undo()
    assert session.get_map(document.id).objects == (item,)
    session.edit_layer(document.id, first.id, visible=False)
    assert session.get_map(document.id).objects == (item,)
    session.move_layer(document.id, first.id, 1)
    assert (
        sorted(session.get_map(document.id).layers, key=lambda layer: layer.position)[1].id
        == first.id
    )
    with pytest.raises(ValueError, match="подтвердите"):
        session.delete_layer(document.id, first.id)
    session.delete_layer(document.id, first.id, delete_contents=True)
    assert not session.get_map(document.id).objects
    session.undo_stack(document.id).undo()
    assert session.get_map(document.id).objects == (item,)
    before = session.get_map(document.id)
    for changes in [dict(width=0), dict(kind="road"), dict(layer_id=str(uuid4())), dict(z=True)]:
        with pytest.raises((ValueError, TypeError)):
            session.edit_object(document.id, item.id, **changes)
        assert session.get_map(document.id) == before
    assert second.id != first.id


def test_object_views_modes_shared_asset_and_backup(project, qtbot, tmp_path):
    app, project = project
    document, widget = open_map(app, project, tmp_path, qtbot)
    session = app.maps_service
    first = session.add_layer(document.id, "Decor")
    second = session.add_layer(document.id, "Upper")
    one = session.add_object(document.id, first.id, document.asset_id, 30, 40, 100, 120)
    two = session.add_object(document.id, second.id, document.asset_id, 130, 140, 100, 120)
    token = session.add_token(document.id, app.create_card("Card").id, 200, 200)
    assert len(project.assets) == 1 and len(widget.view._objects) == 2
    assert (
        not widget.view._objects[one.id].flags()
        & widget.view._objects[one.id].GraphicsItemFlag.ItemIsMovable
    )
    editor = app.maps.open_map_editor(document.id).widget()
    assert (
        editor.view._objects[one.id].flags()
        & editor.view._objects[one.id].GraphicsItemFlag.ItemIsMovable
    )
    assert (
        not editor.view._tokens[0].flags() & editor.view._tokens[0].GraphicsItemFlag.ItemIsMovable
    )
    editor.view.object_moved.emit(one.id, 80, 90)
    assert session.get_map(document.id).objects[0].x == 80
    session.edit_layer(document.id, second.id, visible=False)
    assert not widget.view._objects[two.id].isVisible()
    assert session.get_map(document.id).tokens == (token,)
    session.edit_token(document.id, token.id, layer_id=second.id)
    assert not widget.view._tokens[0].isVisible()
    session.edit_token(document.id, token.id, layer_id=None)
    assert widget.view._tokens[0].isVisible()
    assert widget.token_add.isEnabled()
    assert project.save_current()
    backup = tmp_path / "world.lodbackup"
    project.store.backup(backup)
    restored = SQLiteProjectStore.restore(backup, tmp_path / "restored")
    assert restored.load().maps == project.store.load().maps
    restored.close()
    session.delete_object(document.id, one.id)
    session.undo_stack(document.id).undo()
    assert len(widget.view._objects) == 2
