import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QTextCursor, QTextListFormat
from PySide6.QtWidgets import QInputDialog, QLineEdit

from lodandsy.application.project_catalogue import ProjectCatalogue
from lodandsy.application.sqlite_project_store import DATABASE_NAME
from lodandsy.domain.actor_state import ActorRef
from lodandsy.ui.entity_picker import EntityPicker
from tests.test_map_token_resize import world_mouse
from tests.test_map_tokens_grid import open_map

pytest_plugins = ["tests.project_fixture"]


def test_create_named_world_and_inline_folder(qtbot, project, tmp_path):
    app, projects = project
    projects.catalogue = ProjectCatalogue(lambda: tmp_path / "Мои документы")
    assert projects.create_project("Новый мир")
    assert (projects.store.root / DATABASE_NAME).is_file()
    assert projects.store.root == tmp_path / "Мои документы/LODANDSY/project/Новый мир"
    parent = app.create_card("Места", card_type="folder")
    panel = app.window.tree_panel
    app.window.show()

    def create():
        app.core.select(parent.id)
        next(a for a in panel.create_menu.actions() if a.objectName() == "create-folder").trigger()
        folder = app.cards.get(app.cards_service.current_card_id)
        assert folder.parent_id == parent.id and folder.card_type == "folder"
        editors = panel.tree_view.viewport().findChildren(QLineEdit)
        edit = next(edit for edit in editors if edit.isVisible())
        return folder, edit

    first, edit = create()
    qtbot.keyClick(edit, Qt.Key.Key_Escape)
    assert app.cards.get(first.id).title == "Новая папка"
    second, edit = create()
    assert second.title == "Новая папка 2"
    edit.setText("Архив")
    qtbot.keyClick(edit, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: app.cards.get(second.id).title == "Архив")
    assert projects.save_current()
    assert {card.id for card in projects.store.load().cards} == {parent.id, first.id, second.id}


def test_wiki_search_cancel_replace_undo_and_reopen(qtbot, project, tmp_path):
    app, projects = project
    world = tmp_path / "world"
    assert projects.create_project(world)
    parent = app.create_card("Маршруты", card_type="folder")
    first = app.create_card("Маяк", parent.id, card_type="location")
    second = app.create_card("Маяк", card_type="article")
    note = app.create_card("Путевой журнал")
    editor = app.open_card_editor(note.id).widget()
    edit = editor.text_edit
    qtbot.keyClicks(edit, "[[")
    qtbot.keyClick(editor.wiki_picker.query, Qt.Key.Key_Escape)
    assert editor.wiki_picker is None and edit.toPlainText() == "[["
    edit.clear()
    qtbot.keyClicks(edit, "[[")
    picker = editor.wiki_picker
    picker.query.setText("Маяк")
    assert set(picker.model.ids) == {first.id, second.id}
    first_index = picker.model.index(picker.model.ids.index(first.id))
    assert "Маршруты" in first_index.data()
    assert not first_index.data(Qt.ItemDataRole.DecorationRole).isNull()
    picker.list.setCurrentIndex(first_index)
    qtbot.keyClick(picker.query, Qt.Key.Key_Return)
    href = "lodandsy://entity/" + first.id
    assert href in edit.toHtml() and edit.toPlainText() == "Маяк"
    qtbot.keyClicks(edit, "!")
    assert not edit.textCursor().charFormat().isAnchor()
    edit.undo()
    assert edit.toPlainText() == "Маяк"
    edit.undo()
    assert edit.toPlainText() == "[["
    edit.redo()
    cursor = edit.textCursor()
    cursor.setPosition(1)
    edit.setTextCursor(cursor)
    editor.request_link()
    picker = editor.wiki_picker
    picker.list.setCurrentIndex(picker.model.index(picker.model.ids.index(second.id)))
    qtbot.keyClick(picker.query, Qt.Key.Key_Return)
    href = "lodandsy://entity/" + second.id
    assert href in edit.toHtml()
    selected = edit.link_selection(edit.textCursor(), href)
    assert selected.selectedText() == "Маяк"
    edit.unlink(selected)
    assert href not in edit.toHtml()
    edit.undo()
    assert href in edit.toHtml()
    app.rename_card(second.id, "Башня")
    app.reparent_card(second.id, parent.id)
    assert projects.save_current()
    assert projects.create_project(tmp_path / "second", preserve_current=False)
    projects.open_project(world)
    restored = app.open_card_editor(note.id).widget()
    assert href in restored.text_edit.toHtml()
    cursor = restored.text_edit.textCursor()
    cursor.setPosition(1)
    restored.text_edit.setTextCursor(cursor)
    restored.open_current_link()
    assert app.window_manager.active_window_key == app.card_editor_window_key(second.id)
    app.delete_card(second.id)
    restored.refresh_links()
    assert "Разорванная" in restored.link_status.text() and href in restored.text_edit.toHtml()


def test_heading_selection_and_list_actions_reopen(qtbot, project, tmp_path):
    app, projects = project
    assert projects.create_project(tmp_path / "world")
    card = app.create_card("Абзацы")
    editor = app.open_card_editor(card.id).widget()
    edit, toolbar = editor.text_edit, editor.format_toolbar
    edit.setPlainText("Previous\nOne\nTwo\nNext")

    def levels():
        return [edit.document().findBlockByNumber(i).blockFormat().headingLevel()
                for i in range(edit.document().blockCount())]

    cursor = edit.textCursor()
    cursor.setPosition(9)
    cursor.setPosition(17, QTextCursor.MoveMode.KeepAnchor)
    edit.setTextCursor(cursor)
    toolbar.heading(1)
    assert levels() == [0, 1, 1, 0]
    assert (edit.textCursor().anchor(), edit.textCursor().position()) == (9, 17)
    edit.undo()
    assert levels() == [0, 0, 0, 0]
    edit.redo()
    cursor.setPosition(10)
    edit.setTextCursor(cursor)
    assert toolbar.paragraph.currentIndex() == 1
    toolbar.heading(3)
    assert levels() == [0, 3, 1, 0]
    toolbar.heading(0)
    assert levels() == [0, 0, 1, 0]
    cursor.setPosition(16)
    edit.setTextCursor(cursor)
    qtbot.keyClick(edit, Qt.Key.Key_Return)
    assert levels() == [0, 0, 1, 0, 0]
    assert toolbar.paragraph.currentIndex() == 0
    assert edit.currentCharFormat().fontPointSize() <= 11
    cursor.movePosition(QTextCursor.MoveOperation.End)
    edit.setTextCursor(cursor)
    bullet = toolbar.actions_by_name["bullet"]
    numbered = toolbar.actions_by_name["numbered"]
    assert not bullet.icon().isNull() and bullet.icon().cacheKey() != numbered.icon().cacheKey()
    bullet.trigger()
    assert edit.textCursor().currentList().format().style() == QTextListFormat.Style.ListDisc
    numbered.trigger()
    assert edit.textCursor().currentList().format().style() == QTextListFormat.Style.ListDecimal
    edit.undo()
    assert edit.textCursor().currentList().format().style() == QTextListFormat.Style.ListDisc
    assert projects.save_current()
    app.window_manager.close_window(app.card_editor_window_key(card.id))
    edit = app.open_card_editor(card.id).widget().text_edit
    assert levels() == [0, 0, 1, 0, 0]
    assert edit.document().lastBlock().textList().format().style() == QTextListFormat.Style.ListDisc


def test_collapsible_ability_retains_canonical_values_and_draft(qtbot, project):
    app, _projects = project
    card = app.create_card("Воин", card_type="character")
    ref = app.cards_service.create_actor(card.id)
    actor = app.card_views.open_game_sheet(card.id, ref.actor_id).widget().game_sheet
    tile = actor.tiles["strength"]
    score, modifier = tile.edit.text(), tile.result.text()
    original = app.cards.get(card.id).payload()
    assert not tile.disclosure.isChecked()
    tile.disclosure.setChecked(True)
    qtbot.waitUntil(lambda: tile.height() >= tile.sizeHint().height())
    expanded_height = tile.height()
    tile.disclosure.click()
    assert tile.disclosure.body.isHidden() and not tile.edit.isHidden()
    qtbot.waitUntil(lambda: tile.height() < expanded_height)
    assert (tile.edit.text(), tile.result.text()) == (score, modifier)
    assert app.cards.get(card.id).payload() == original
    tile.disclosure.click()
    assert not tile.disclosure.body.isHidden()
    base = app.card_views.open_game_sheet(card.id).widget().game_sheet.tiles["strength"]
    qtbot.keyClick(base.edit, Qt.Key.Key_End)
    qtbot.keyClicks(base.edit, "x")
    draft = base.edit.text()
    base.disclosure.click()
    base.disclosure.click()
    assert base.edit.text() == draft


def test_map_note_tool_reuses_windows_and_restores_them(project, tmp_path, qtbot, monkeypatch):
    app, projects = project
    document, viewer = open_map(app, projects, tmp_path, qtbot)
    world = projects.store.root
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Дневник", True))
    card = app.create_card("Воин", card_type="character")
    ref = app.cards_service.create_actor(card.id)
    inventory_id = app.cards_service.get_actor(ref).inventory_id
    modes = iter((0, 0, 1))
    monkeypatch.setattr(QInputDialog, "getItem", lambda *args: (args[3][next(modes)], True))

    def exec_picker(picker):
        if "инвентарь" in picker.windowTitle():
            wanted = inventory_id
        elif not picker.model.ids:
            return EntityPicker.CREATE
        else:
            wanted = next(c.id for c in app.cards.all() if c.title == "Дневник")
        assert wanted in picker.model.ids
        picker.chosen_id = wanted
        return 1

    monkeypatch.setattr(EntityPicker, "exec", exec_picker)
    for x in (90, 175, 315):
        viewer.tools.actions["note"].trigger()
        qtbot.mouseClick(viewer.view.viewport(), Qt.MouseButton.LeftButton,
                         pos=viewer.view.mapFromScene(QPointF(x, 100)))
    saved = app.maps_service.get_map(document.id)
    first, second, third = saved.notes
    assert first.id != second.id and first.target_id == second.target_id
    assert third.target_kind == "inventory" and third.target_id == inventory_id
    player = app.maps.open_presentation(document.id)
    qtbot.waitUntil(lambda: player.view._display_ready)
    assert not player.view.vector_notes
    qtbot.mouseDClick(viewer.view.viewport(), Qt.MouseButton.LeftButton,
                     pos=viewer.view.mapFromScene(QPointF(first.x, first.y)))
    key = app.card_editor_window_key(first.target_id)
    note_window = app.window_manager.find_window(key)
    assert note_window.dock.isInFloatingContainer()
    assert app.maps._note_action(document.id, second.id, "open") is note_window
    inventory = app.maps._note_action(document.id, third.id, "open")
    assert app.tables.open_table(inventory_id) is inventory
    assert inventory.dock.isInFloatingContainer()
    app.maps.open_map(document.id)
    start = QPointF(first.x, first.y)
    end = start + QPointF(28, 30)
    world_mouse(viewer.view, QEvent.Type.MouseButtonPress, start)
    world_mouse(viewer.view, QEvent.Type.MouseMove, end)
    assert app.maps_service.get_map(document.id) == saved
    world_mouse(viewer.view, QEvent.Type.MouseButtonRelease, end)
    assert app.maps_service.get_map(document.id).notes[0].x == pytest.approx(end.x())
    stack = app.maps_service.undo_stack(document.id)
    stack.undo()
    assert app.maps_service.get_map(document.id) == saved
    stack.redo()
    app.maps._note_action(document.id, second.id, "rename")
    assert app.maps_service.get_map(document.id).notes[1].label == "Дневник"
    monkeypatch.setattr(QInputDialog, "getItem", lambda *args: (args[3][1], True))
    app.maps._note_action(document.id, second.id, "rebind")
    assert app.maps_service.get_map(document.id).notes[1].target_id == inventory_id
    app.maps._note_action(document.id, second.id, "delete")
    assert app.tables_service.get_table(inventory_id).id == inventory_id
    assert app.cards.get(first.target_id).card_type == "note"
    assert projects.save_current()
    assert projects.create_project(tmp_path / "another", preserve_current=False)
    assert not app.window_manager.window_keys()
    projects.open_project(world)
    for key in (note_window.key, inventory.key):
        assert app.window_manager.find_window(key).dock.isInFloatingContainer()
    app.actions.delete_actor(ref, confirmed=True)
    assert app.window_manager.find_window(inventory.key) is None
    assert app.maps_service.get_map(document.id).notes[-1] == third
    restored = app.maps.open_map(document.id).widget()
    assert restored.view.note_labels[third.id][1] is False
    assert app.maps._note_action(document.id, third.id, "open") is None


def test_inspector_tracks_active_map_and_temporary_pan(qtbot, project, tmp_path):
    app, projects = project
    first, viewer = open_map(app, projects, tmp_path, qtbot)
    inspector = app.window.inspector_panel
    viewer.tool_state.activate("fog_hide")
    assert inspector.pages.currentWidget() is viewer.tools.context
    assert not viewer.isAncestorOf(viewer.fog_tools)
    viewer.fog_tools.size.setValue(240)
    qtbot.keyPress(viewer.view.viewport(), Qt.Key.Key_Space)
    assert viewer.tool_state.active == "pan" and viewer.fog_tools.isHidden()
    qtbot.keyRelease(viewer.view.viewport(), Qt.Key.Key_Space)
    assert viewer.tool_state.active == "fog_hide" and viewer.fog_tools.size.value() == 240
    second = app.maps_service.create_map("Другая карта", first.asset_id)
    second_window = app.maps.open_map(second.id)
    other = second_window.widget()
    other.tool_state.activate("rectangle")
    assert inspector.pages.currentWidget() is other.tools.context
    viewer.tool_state.activate("fog_erase")
    assert inspector.pages.currentWidget() is other.tools.context
    app.window_manager.find_window("map:" + first.id).dock.tabWidget().clicked.emit()
    assert inspector.pages.currentWidget() is viewer.tools.context
    viewer.tool_state.activate("select")
    assert not inspector.feature_page_active
    card = app.create_card("Дозорный", card_type="character")
    token = app.actions.place_card(first.id, card.id, 100, 100)
    viewer.view.select_token(token.id)
    assert inspector.context_control is viewer.tools.measurement
    assert inspector.title_edit.text() == app.cards_service.get_actor(
        ActorRef(card.id, token.actor_id)
    ).name
    previous = viewer.view.measurement_mode
    combo = viewer.tools.measurement_mode
    for mode in ("geometry", previous):
        combo.activated.emit(combo.findData(mode))
        assert viewer.view.measurement_mode == mode
    viewer.view.select_token(None)
    assert inspector.context_control is None
    second_window.close()
    assert inspector.pages.indexOf(other.tools.context) < 0
