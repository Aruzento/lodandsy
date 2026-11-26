from uuid import uuid4

from PySide6.QtCore import QEvent, QModelIndex, QPoint, QPointF, QSize, Qt, QTimer
from PySide6.QtGui import QImage, QMouseEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.application.workspace_state import capture_workspace, restore_workspace
from lodandsy.domain.card import Card
from lodandsy.domain.document_payloads import project_entities
from lodandsy.domain.map_document import MapDocument
from lodandsy.ui.card_creation_dialog import CardCreationDialog
from lodandsy.ui.project_tree_model import NODE_ID_ROLE, NODE_KIND_ROLE, ProjectTreeModel
from lodandsy.ui.tree_panel import TreePanel
from tests.project_fixture import text_table

pytest_plugins = ["tests.project_fixture"]


def mixed_model():
    parent = Card("Parent")
    child = Card("Child", parent_id=parent.id)
    document = MapDocument("Map", str(uuid4()))
    table = text_table("Table")
    entities = project_entities((parent, child), (document,), (table,))
    entities.update(document.id, parent_id=parent.id)
    entities.update(table.id, parent_id=document.id)
    model = ProjectTreeModel()
    model.set_entities(entities.summaries())
    return model, entities, parent, child, document, table


def test_project_tree_uses_one_canonical_mixed_hierarchy(qapp):
    model, entities, parent, child, document, table = mixed_model()
    assert model.rowCount() == 1
    assert not model.index_for_node("card:" + parent.id).parent().isValid()
    assert model.index_for_node("card:" + child.id).parent() == model.index_for_node(
        "card:" + parent.id
    )
    assert model.index_for_node(f"map:{document.id}").parent() == model.index_for_node(
        "card:" + parent.id
    )
    assert model.index_for_node(f"table:{table.id}").parent().data() == "Map"
    assert all(not key.startswith("section:") for key in model.node_keys())
    assert model.index_for_node(f"map:{document.id}").data(NODE_ID_ROLE) == document.id
    assert model.index_for_node(f"table:{table.id}").data(NODE_KIND_ROLE) == "table"


def test_all_document_kinds_can_drag_root_drop_and_mixed_cycles_are_rejected(qtbot):
    model, entities, parent, child, document, table = mixed_model()
    for kind, item in [("card", parent), ("map", document), ("table", table)]:
        index = model.index_for_node(f"{kind}:{item.id}")
        assert model.flags(index) & Qt.ItemFlag.ItemIsDragEnabled
        data = model.mimeData([index])
        assert not model.canDropMimeData(data, Qt.DropAction.MoveAction, -1, 0, index)
        assert model.canDropMimeData(data, Qt.DropAction.MoveAction, -1, 0, QModelIndex())
    data = model.mimeData([model.index_for_node("card:" + parent.id)])
    assert not model.canDropMimeData(
        data, Qt.DropAction.MoveAction, -1, 0, model.index_for_node(f"table:{table.id}")
    )
    data = model.mimeData([model.index_for_node("card:" + child.id)])
    with qtbot.waitSignal(model.move_requested) as signal:
        assert model.dropMimeData(data, Qt.DropAction.MoveAction, 1, 0, QModelIndex())
    assert signal.args == [child.id, None, 1]


def test_title_update_preserves_indices_without_duplicate_payload_state(qapp):
    model, entities, parent, child, document, table = mixed_model()
    first = model.itemFromIndex(model.index_for_node(f"map:{document.id}"))
    entities.update(document.id, title="Renamed")
    model.set_entities(entities.summaries())
    assert model.itemFromIndex(model.index_for_node(f"map:{document.id}")) is first
    assert first.text() == "Renamed"
    entities.delete(document.id)
    model.set_entities(entities.summaries())
    assert not model.index_for_node(f"table:{table.id}").isValid()
    assert not model.index_for_node(f"table:{table.id}").isValid()
    assert model.index_for_node("card:" + parent.id).isValid()


def action(menu, name):
    return next(item for item in menu.actions() if item.objectName() == name)


def move_over(viewport, point):
    QApplication.sendEvent(viewport, QMouseEvent(
        QEvent.Type.MouseMove, QPointF(point), QPointF(viewport.mapToGlobal(point)),
        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    ))


def visit_context_menu(panel, monkeypatch, visit):
    create = panel.context_menu

    def context_menu(index=None):
        menu = create(index)

        def inspect():
            try:
                visit(menu)
            finally:
                menu.close()

        menu.aboutToShow.connect(lambda: QTimer.singleShot(0, inspect))
        return menu

    monkeypatch.setattr(panel, "context_menu", context_menu)


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
    qtbot.waitUntil(lambda: not app.maps.importing)
    document = next(iter(app.maps_service.maps.values()))
    assert panel.tree_model.index_for_node(f"map:{document.id}").data() == "From tree"
    action(panel.create_menu, "create-table").trigger()
    table = next(iter(app.tables_service.tables.values()))
    assert panel.tree_model.index_for_node(f"table:{table.id}").data() == "From tree"
    assert not app.cards.all()
    assert not {"Карточки", "Карты"}.intersection(
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
    with qtbot.waitActive(app.window):
        app.window.activateWindow()
    panel.tree_view.setFocus()
    qtbot.waitUntil(panel.tree_view.hasFocus)
    qtbot.keyClick(panel.tree_view, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(app._search_dialog.isVisible)


def test_row_action_opens_document_and_pins_to_its_row_during_menu(project, qtbot, monkeypatch):
    app, project = project
    app.window.show()
    card = app.create_card("Root")
    other = app.create_card("Other")
    panel = app.window.tree_panel
    tree, actions = panel.tree_view, panel.inline_actions
    index = panel.tree_model.index_for_node(f"card:{card.id}")
    other_index = panel.tree_model.index_for_node(f"card:{other.id}")
    tree.setCurrentIndex(other_index)
    viewport = tree.viewport()
    button = actions.menu_button
    before = tree.visualRect(index)
    move_over(viewport, QPoint(0, viewport.height() - 2))
    assert not button.isVisible()
    move_over(viewport, before.center())
    assert button.isVisible() and actions.index == index and tree.currentIndex() == other_index
    assert button.size() == QSize(24, 24)
    assert tree.visualRect(index) == before

    def open_document(menu):
        move_over(viewport, tree.visualRect(other_index).center())
        assert button.isVisible() and actions.index == index
        assert menu.actions()[0] == action(menu, "open")
        assert not action(menu, "child").menu().isVisible()
        action(menu, "open").trigger()

    visit_context_menu(panel, monkeypatch, open_document)
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    first = app.window_manager.find_window(f"card-editor:{card.id}")
    assert first is not None
    move_over(viewport, before.center())
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert app.window_manager.find_window(f"card-editor:{card.id}") is first
    monkeypatch.setattr(CardCreationDialog, "get_card", lambda *a: ("Child", "note", False, True))
    menu = panel.context_menu(index)
    action(action(menu, "child").menu(), "create-card").trigger()
    assert app.cards.child_ids(card.id)
    assert app.cards.get(app.cards.child_ids(card.id)[0]).title == "Child"


def test_mixed_rows_keep_same_hover_geometry_and_context_menu_shortcut(qtbot, monkeypatch):
    panel = TreePanel()
    qtbot.addWidget(panel)
    panel.resize(180, 280)
    panel.show()
    tree, model = panel.tree_view, panel.tree_model
    _, entities, _, _, document, table = mixed_model()
    panel.set_entities(entities.summaries())
    tree.expandAll()
    rows = [model.index_for_node(key) for key in model.node_keys()]
    button = panel.inline_actions.menu_button
    for row in rows:
        before = tree.visualRect(row)
        move_over(tree.viewport(), before.center())
        assert panel.inline_actions.index == row and button.isVisible()
        assert tree.visualRect(row) == before
        assert button.geometry().right() == tree.viewport().width() - 5

    table_row = model.index_for_node(f"table:{table.id}")
    tree.setCurrentIndex(table_row)
    move_over(tree.viewport(), QPoint(0, tree.viewport().height() - 2))
    assert not button.isVisible()
    menus = []

    def visit_menu(menu):
        assert panel.inline_actions.index == table_row and button.isVisible()
        assert action(menu, "open").isEnabled()
        menus.append(menu)

    visit_context_menu(panel, monkeypatch, visit_menu)
    with qtbot.waitActive(panel):
        panel.activateWindow()
    tree.setFocus()
    qtbot.keyClick(tree, Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)
    assert len(menus) == 1
    map_row = model.index_for_node(f"map:{document.id}")
    assert action(panel.context_menu(map_row), "open").isEnabled()


def test_enter_opens_dice_and_table_and_selection_does_not_retarget_cards(project, qtbot):
    app, project = project
    app.window.show()
    card = app.create_card("Card")
    editor = app.open_card_editor(card.id).widget()
    editor.text_edit.insertPlainText("Keep")
    table = app.tables_service.create_table("Table")
    panel = app.window.tree_panel
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_node(f"table:{table.id}"))
    panel.tree_view.setFocus()
    qtbot.keyClick(panel.tree_view, Qt.Key.Key_Return)
    assert app.window_manager.find_window(f"table:{table.id}") is not None
    assert app.cards_service.current_card_id is None
    assert app.window.inspector_panel.title_edit.text() == "Table"
    assert not app.window.inspector_panel.title_edit.isReadOnly()
    assert app.cards_service.current_entity_id == table.id
    assert editor.card_id == card.id and editor.text_edit.toPlainText() == "Keep"
    dice = app.dice.open()
    assert app.window_manager.find_window("tool:dice") is dice
    assert app.window.inspector_panel.id_edit.text() == table.id


def test_module_rename_delete_updates_summary_and_closes_only_its_document(project, monkeypatch):
    app, project = project
    card = app.create_card("Card")
    editor = app.open_card_editor(card.id)
    table = app.tables_service.create_table("Table")
    app.tables.open_table(table.id)
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
    document = app.maps_service.create_map("Map", str(uuid4()))
    panel = app.window.tree_panel
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_node(f"map:{document.id}"))
    panel.tree_view.setExpanded(panel.tree_model.index_for_node("card:" + card.id), False)
    data = capture_workspace(app)
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_node("card:" + card.id))
    panel.tree_view.expandAll()
    restore_workspace(app, data)
    assert panel.current_node_key() == f"map:{document.id}"
    assert app.navigator_selection == f"map:{document.id}"
    assert app.cards_service.current_card_id is None
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
    assert not hasattr(app.maps_service, "dice")
    assert set(app.window_manager.window_keys()) == {f"card-editor:{card.id}"}


def test_collapsed_modules_stay_collapsed_when_title_or_cards_change(project):
    app, project = project
    table = app.tables_service.create_table("Table")
    panel = app.window.tree_panel
    panel.tree_view.setExpanded(panel.tree_model.index_for_node(f"table:{table.id}"), False)
    app.tables_service.edit_table(table.id, title="Renamed")
    app.create_card("New")
    assert not panel.tree_view.isExpanded(panel.tree_model.index_for_node(f"table:{table.id}"))
