from uuid import uuid4

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.application.workspace_state import capture_workspace, restore_workspace
from lodandsy.domain.card import Card
from lodandsy.domain.dice_document import DiceDocument
from lodandsy.domain.document_payloads import project_entities
from lodandsy.domain.map_document import MapDocument
from lodandsy.ui.card_creation_dialog import CardCreationDialog
from lodandsy.ui.project_tree_model import NODE_ID_ROLE, NODE_KIND_ROLE, ProjectTreeModel
from tests.project_fixture import text_table

pytest_plugins = ["tests.project_fixture"]


def mixed_model():
    parent = Card("Parent")
    child = Card("Child", parent_id=parent.id)
    document = MapDocument("Map", str(uuid4()))
    table = text_table("Table")
    dice = DiceDocument("Dice")
    entities = project_entities((parent, child), (document,), (table,), (dice,))
    entities.update(document.id, parent_id=parent.id)
    entities.update(table.id, parent_id=document.id)
    entities.update(dice.id, parent_id=table.id)
    model = ProjectTreeModel()
    model.set_entities(entities.summaries())
    return model, entities, parent, child, document, table, dice


def test_project_tree_uses_one_canonical_mixed_hierarchy(qapp):
    model, entities, parent, child, document, table, dice = mixed_model()
    assert model.rowCount() == 1
    assert not model.index_for_node("card:" + parent.id).parent().isValid()
    assert model.index_for_node("card:" + child.id).parent() == model.index_for_node(
        "card:" + parent.id
    )
    assert model.index_for_node(f"map:{document.id}").parent() == model.index_for_node(
        "card:" + parent.id
    )
    assert model.index_for_node(f"table:{table.id}").parent().data() == "Map"
    assert model.index_for_node(f"dice:{dice.id}").parent().data() == "Table"
    assert all(not key.startswith("section:") for key in model.node_keys())
    assert model.index_for_node(f"map:{document.id}").data(NODE_ID_ROLE) == document.id
    assert model.index_for_node(f"table:{table.id}").data(NODE_KIND_ROLE) == "table"


def test_all_document_kinds_can_drag_root_drop_and_mixed_cycles_are_rejected(qtbot):
    model, entities, parent, child, document, table, dice = mixed_model()
    for kind, item in [("card", parent), ("map", document), ("table", table), ("dice", dice)]:
        index = model.index_for_node(f"{kind}:{item.id}")
        assert model.flags(index) & Qt.ItemFlag.ItemIsDragEnabled
        data = model.mimeData([index])
        assert not model.canDropMimeData(data, Qt.DropAction.MoveAction, -1, 0, index)
        assert model.canDropMimeData(data, Qt.DropAction.MoveAction, -1, 0, QModelIndex())
    data = model.mimeData([model.index_for_node("card:" + parent.id)])
    assert not model.canDropMimeData(
        data, Qt.DropAction.MoveAction, -1, 0, model.index_for_node(f"dice:{dice.id}")
    )
    data = model.mimeData([model.index_for_node("card:" + child.id)])
    with qtbot.waitSignal(model.move_requested) as signal:
        assert model.dropMimeData(data, Qt.DropAction.MoveAction, 1, 0, QModelIndex())
    assert signal.args == [child.id, None, 1]


def test_title_update_preserves_indices_without_duplicate_payload_state(qapp):
    model, entities, parent, child, document, table, dice = mixed_model()
    first = model.itemFromIndex(model.index_for_node(f"map:{document.id}"))
    entities.update(document.id, title="Renamed")
    model.set_entities(entities.summaries())
    assert model.itemFromIndex(model.index_for_node(f"map:{document.id}")) is first
    assert first.text() == "Renamed"
    entities.delete(document.id)
    model.set_entities(entities.summaries())
    assert not model.index_for_node(f"table:{table.id}").isValid()
    assert not model.index_for_node(f"dice:{dice.id}").isValid()
    assert model.index_for_node("card:" + parent.id).isValid()


def action(menu, name):
    return next(item for item in menu.actions() if item.objectName() == name)


def test_create_map_and_table_from_plus_menu_without_top_navigation(
    project, tmp_path, qtbot, monkeypatch
):
    app, project = project
    project.create_project(tmp_path / "world")
    source = tmp_path / "map.png"
    image = QImage(100, 100, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.darkBlue)
    image.save(str(source))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(source), ""))
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("From tree", True))
    panel = app.window.tree_panel
    action(panel.create_menu, "create-map").trigger()
    assert not action(panel.create_menu, "create-map").isEnabled()
    qtbot.waitUntil(lambda: not app.modules.importing)
    document = next(iter(app.modules.session.maps.values()))
    assert panel.tree_model.index_for_node(f"map:{document.id}").data() == "From tree"
    action(panel.create_menu, "create-table").trigger()
    table = next(iter(app.modules.session.tables.values()))
    assert panel.tree_model.index_for_node(f"table:{table.id}").data() == "From tree"
    assert not app.cards.all()
    assert not {"Карточки", "Карты", "Инструменты"}.intersection(
        item.text() for item in app.window.menuBar().actions()
    )
    assert project.save_current()
    assert project.store.load().maps[0].id == document.id
    assert project.store.load().tables[0].id == table.id
    folder = project.store.root
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_node(f"table:{table.id}"))
    other = SQLiteProjectStore.create(tmp_path / "other")
    other.close()
    project.open_project(tmp_path / "other")
    assert panel.tree_model.rowCount() == 0
    project.open_project(folder)
    assert panel.tree_model.index_for_node(f"map:{document.id}").data() == "From tree"
    assert panel.tree_model.index_for_node(f"table:{table.id}").data() == "From tree"
    assert panel.current_node_key() == f"table:{table.id}"
    assert not project.saver.dirty


def test_search_is_opened_from_button_and_shortcut_without_duplicate_menu(project, qtbot):
    app, project = project
    app.window.show()
    panel = app.window.tree_panel
    qtbot.mouseClick(panel.search_button, Qt.MouseButton.LeftButton)
    assert app._search_dialog.isVisible()
    app._search_dialog.close()
    app.window.activateWindow()
    panel.tree_view.setFocus()
    qtbot.waitUntil(app.window.isActiveWindow)
    qtbot.keyClick(panel.tree_view, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert app._search_dialog.isVisible()


def test_selected_row_buttons_open_and_child_creation_is_contextual(project, qtbot, monkeypatch):
    app, project = project
    app.window.show()
    card = app.create_card("Root")
    panel = app.window.tree_panel
    index = panel.tree_model.index_for_node("card:" + card.id)
    panel.tree_view.setCurrentIndex(index)
    qtbot.waitUntil(lambda: panel.inline_actions.open_button.isVisible())
    qtbot.mouseClick(panel.inline_actions.open_button, Qt.MouseButton.LeftButton)
    assert len(app.cards.all()) == 1
    first = app.window_manager.find_window(f"card-editor:{card.id}")
    assert first is not None
    qtbot.mouseClick(panel.inline_actions.open_button, Qt.MouseButton.LeftButton)
    assert app.window_manager.find_window(f"card-editor:{card.id}") is first
    monkeypatch.setattr(CardCreationDialog, "get_card", lambda *a: ("Child", "empty", True))
    menu = panel.context_menu(index)
    action(action(menu, "child").menu(), "create-card").trigger()
    assert app.cards.child_ids(card.id)
    assert app.cards.get(app.cards.child_ids(card.id)[0]).title == "Child"


def test_enter_opens_dice_and_table_and_selection_does_not_retarget_cards(project, qtbot):
    app, project = project
    app.window.show()
    card = app.create_card("Card")
    editor = app.open_card_editor(card.id).widget()
    editor.text_edit.insertPlainText("Keep")
    table = app.modules.session.create_table("Table")
    panel = app.window.tree_panel
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_node(f"table:{table.id}"))
    panel.tree_view.setFocus()
    qtbot.keyClick(panel.tree_view, Qt.Key.Key_Return)
    assert app.window_manager.find_window(f"table:{table.id}") is not None
    assert app.session.current_card_id is None
    assert app.window.inspector_panel.title_edit.text() == "Table"
    assert not app.window.inspector_panel.title_edit.isReadOnly()
    assert app.session.current_entity_id == table.id
    assert editor.card_id == card.id and editor.text_edit.toPlainText() == "Keep"
    dice = app.modules.session.create_dice("Checks", table.id)
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_node(f"dice:{dice.id}"))
    qtbot.keyClick(panel.tree_view, Qt.Key.Key_Return)
    assert app.window_manager.find_window(f"dice:{dice.id}") is not None
    assert app.window.inspector_panel.id_edit.text() == dice.id


def test_module_rename_delete_updates_summary_and_closes_only_its_document(project, monkeypatch):
    app, project = project
    card = app.create_card("Card")
    editor = app.open_card_editor(card.id)
    table = app.modules.session.create_table("Table")
    app.modules.open_table(table.id)
    panel = app.window.tree_panel
    index = panel.tree_model.index_for_node(f"table:{table.id}")
    panel.tree_view.setCurrentIndex(index)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Renamed", True))
    menu = panel.context_menu(index)
    action(menu, "rename").trigger()
    assert index.data() == "Renamed"
    assert app.window.inspector_panel.title_edit.text() == "Renamed"
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    action(menu, "delete").trigger()
    assert not panel.tree_model.index_for_node(f"table:{table.id}").isValid()
    assert app.window_manager.find_window(f"table:{table.id}") is None
    assert app.window_manager.find_window(f"card-editor:{card.id}") is editor
    assert panel.current_node_key() is None
    assert not app.window.inspector_panel.id_edit.text()


def test_navigator_selection_and_expansion_roundtrip_separate_from_active_document(project):
    app, project = project
    card = app.create_card("Card")
    app.open_card_editor(card.id)
    document = app.modules.session.create_map("Map", str(uuid4()))
    panel = app.window.tree_panel
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_node(f"map:{document.id}"))
    panel.tree_view.setExpanded(panel.tree_model.index_for_node("card:" + card.id), False)
    data = capture_workspace(app)
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_node("card:" + card.id))
    panel.tree_view.expandAll()
    restore_workspace(app, data)
    assert panel.current_node_key() == f"map:{document.id}"
    assert app.navigator_selection == f"map:{document.id}"
    assert app.session.current_card_id is None
    assert not panel.tree_view.isExpanded(panel.tree_model.index_for_node("card:" + card.id))
    assert app.window_manager.active_window_key == f"card-editor:{card.id}"
    assert not project.store


def test_obsolete_workspace_state_is_rejected_without_creating_documents(project):
    import pytest

    app, _ = project
    card = app.create_card("Card")
    app.open_card_editor(card.id)
    data = capture_workspace(app)
    data["version"] = 1
    data["documents"].append("dice")
    with pytest.raises(ValueError, match="версия раскладки"):
        restore_workspace(app, data)
    assert not app.modules.session.dice
    assert set(app.window_manager.window_keys()) == {f"card-editor:{card.id}"}


def test_collapsed_modules_stay_collapsed_when_title_or_cards_change(project):
    app, project = project
    table = app.modules.session.create_table("Table")
    panel = app.window.tree_panel
    panel.tree_view.setExpanded(panel.tree_model.index_for_node(f"table:{table.id}"), False)
    app.modules.session.edit_table(table.id, title="Renamed")
    app.create_card("New")
    assert not panel.tree_view.isExpanded(panel.tree_model.index_for_node(f"table:{table.id}"))
