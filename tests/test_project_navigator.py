from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.application.workspace_state import capture_workspace, restore_workspace
from lodandsy.domain.card import Card
from lodandsy.ui.card_creation_dialog import CardCreationDialog
from lodandsy.ui.card_tree_model import CARD_ID_ROLE
from lodandsy.ui.project_tree_model import NODE_KIND_ROLE, ProjectTreeModel

pytest_plugins = ["tests.project_fixture"]


def test_project_sections_keep_card_hierarchy_and_separate_module_ids(qapp):
    model = ProjectTreeModel()
    parent = Card("Parent")
    child = Card("Child", parent_id=parent.id)
    model.set_cards((parent, child))
    model.set_module_entries("map", ((parent.id, "Map"),))
    model.set_module_entries("table", ((child.id, "Table"),))
    assert model.rowCount() == 4
    assert model.index_for_card(parent.id).parent() == model.section_index("card")
    assert model.index_for_card(child.id).parent() == model.index_for_card(parent.id)
    assert model.index_for_node(f"map:{parent.id}").data(CARD_ID_ROLE) is None
    assert model.index_for_node(f"table:{child.id}").data(NODE_KIND_ROLE) == "table"
    model.set_cards((parent,))
    assert model.index_for_node(f"map:{parent.id}").data() == "Map"


def test_only_cards_can_drag_and_only_card_branch_accepts_drop(qtbot):
    model = ProjectTreeModel()
    first, second = Card("First"), Card("Second")
    child = Card("Child", parent_id=first.id)
    model.set_cards((first, child, second))
    model.set_module_entries("map", ((first.id, "Map"),))
    data = model.mimeData([model.index_for_card(first.id)])
    assert not model.canDropMimeData(data, Qt.DropAction.MoveAction, -1, 0,
                                     model.section_index("map"))
    assert not model.canDropMimeData(data, Qt.DropAction.MoveAction, -1, 0,
                                     model.index_for_card(child.id))
    assert not (model.flags(model.index_for_node(f"map:{first.id}"))
                & Qt.ItemFlag.ItemIsDragEnabled)
    with qtbot.waitSignal(model.move_requested) as signal:
        assert model.dropMimeData(data, Qt.DropAction.MoveAction, 2, 0,
                                  model.section_index("card"))
    assert signal.args == [first.id, None, 1]


def test_module_title_update_and_delete_do_not_reset_other_nodes(qapp):
    model = ProjectTreeModel()
    model.set_module_entries("map", (("one", "One"), ("two", "Two")))
    first = model.itemFromIndex(model.index_for_node("map:one"))
    model.set_module_entries("map", (("one", "Renamed"),))
    assert model.itemFromIndex(model.index_for_node("map:one")) is first
    assert first.text() == "Renamed"
    assert not model.index_for_node("map:two").isValid()


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
        item.text() for item in app.window.menuBar().actions())
    assert project.save_current()
    assert project.store.load().maps[0].id == document.id
    assert project.store.load().tables[0].id == table.id
    folder = project.store.root
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_node(f"table:{table.id}"))
    other = SQLiteProjectStore.create(tmp_path / "other")
    other.close()
    project.open_project(tmp_path / "other")
    assert panel.tree_model.rowCount(panel.tree_model.section_index("map")) == 0
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
    index = panel.tree_model.index_for_card(card.id)
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
    action(menu, "child").trigger()
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
    assert app.window.inspector_panel.title_edit.isReadOnly()
    assert editor.card_id == card.id and editor.text_edit.toPlainText() == "Keep"
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_node("dice:dice"))
    qtbot.keyClick(panel.tree_view, Qt.Key.Key_Return)
    assert app.window_manager.find_window("dice") is not None
    assert app.window.inspector_panel.id_edit.text() == ""


def test_module_rename_delete_updates_summary_and_closes_only_its_document(
    project, monkeypatch
):
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
    assert panel.current_node_key() == "section:table"
    assert not app.window.inspector_panel.id_edit.text()


def test_navigator_selection_and_expansion_roundtrip_separate_from_active_document(project):
    app, project = project
    card = app.create_card("Card")
    app.open_card_editor(card.id)
    document = app.modules.session.create_map("Map", str(uuid4()))
    panel = app.window.tree_panel
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_node(f"map:{document.id}"))
    panel.tree_view.setExpanded(panel.tree_model.section_index("card"), False)
    data = capture_workspace(app)
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_card(card.id))
    panel.tree_view.expandAll()
    restore_workspace(app, data)
    assert panel.current_node_key() == f"map:{document.id}"
    assert app.navigator_selection == f"map:{document.id}"
    assert app.session.current_card_id is None
    assert not panel.tree_view.isExpanded(panel.tree_model.section_index("card"))
    assert app.window_manager.active_window_key == f"card-editor:{card.id}"
    assert not project.store


def test_legacy_workspace_state_expands_new_card_section(project):
    app, project = project
    card = app.create_card("Card")
    app.open_card_editor(card.id)
    data = capture_workspace(app)
    for key in ["navigator_selected", "navigator_expanded", "navigator_scroll"]:
        data.pop(key)
    app.window.tree_panel.tree_view.collapseAll()
    restore_workspace(app, data)
    assert app.window.tree_panel.current_node_key() == f"card:{card.id}"
    assert app.window.tree_panel.tree_view.isExpanded(
        app.window.tree_panel.tree_model.section_index("card"))


def test_collapsed_modules_stay_collapsed_when_title_or_cards_change(project):
    app, project = project
    table = app.modules.session.create_table("Table")
    panel = app.window.tree_panel
    panel.tree_view.setExpanded(panel.tree_model.section_index("table"), False)
    app.modules.session.edit_table(table.id, title="Renamed")
    app.create_card("New")
    assert not panel.tree_view.isExpanded(panel.tree_model.section_index("table"))
