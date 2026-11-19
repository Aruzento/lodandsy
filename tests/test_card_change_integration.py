from uuid import uuid4

import pytest
from PySide6.QtGui import QTextCursor

from lodandsy.application.app_controller import AppController
from lodandsy.application.card_editor_binding import CardEditorBinding
from lodandsy.application.rich_html import html_text, text_document
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.card_editor import CardEditorWidget
from lodandsy.ui.project_tree_model import NODE_ID_ROLE


def make_controller(qtbot):
    cards = CardCollection()
    a = cards.create("A")
    child = cards.create("Child", a.id)
    b = cards.create("B")
    cards.create("B child", b.id)
    window = AppShell()
    qtbot.addWidget(window)
    return AppController(window, cards), a, child, b


def test_tree_keeps_selection_and_collapsed_branches_after_all_commands(qtbot):
    controller, a, child, b = make_controller(qtbot)
    panel = controller.window.tree_panel
    model, view = panel.tree_model, panel.tree_view
    view.collapse(model.index_for_node("card:" + b.id))
    view.setCurrentIndex(model.index_for_node("card:" + child.id))
    selection_events = []
    controller.session.current_card_changed.connect(selection_events.append)
    for operation in [
        lambda: controller.rename_card(child.id, "Renamed"),
        lambda: controller.create_card("New", a.id),
        lambda: controller.reparent_card(child.id, b.id),
        lambda: controller.delete_card(a.id),
    ]:
        operation()
        assert view.currentIndex().data(NODE_ID_ROLE) == child.id
        assert controller.session.current_card_id == child.id
        assert not view.isExpanded(model.index_for_node("card:" + b.id))
        assert controller.window.inspector_panel.id_edit.text() == child.id
    assert selection_events == []
    controller.delete_card(b.id)
    assert controller.session.current_card_id is None
    assert not view.currentIndex().isValid()
    assert selection_events == [None]


def test_session_changes_update_views_once_and_skip_noops_and_failures(qtbot):
    controller, a, child, b = make_controller(qtbot)
    session = controller.session
    session.select_card(child.id)
    editor = CardEditorWidget()
    qtbot.addWidget(editor)
    binding = CardEditorBinding(session, editor, child.id)
    changes = []
    session.card_changed.connect(lambda *args: changes.append(args))
    session.update_card(child.id, title="Renamed", parent_id=b.id, content=text_document("Text"))
    assert changes == [(child.id, frozenset({"title", "parent_id", "position", "description"}))]
    panel = controller.window.tree_panel
    assert panel.tree_model.index_for_node("card:" + child.id).data() == "Renamed"
    assert panel.tree_model.index_for_node("card:" + child.id).parent().data(NODE_ID_ROLE) == b.id
    assert editor.text_edit.toPlainText() == "Text"
    assert controller.window.inspector_panel.title_edit.text() == "Renamed"
    session.update_card(child.id, title="Renamed", content=text_document("Text"))
    with pytest.raises(ValueError):
        session.update_card(child.id, title="Bad", parent_id=str(uuid4()))
    assert len(changes) == 1
    assert session.cards.get(child.id).title == "Renamed"
    assert binding.session is session


def test_two_views_synchronize_without_resetting_origin_undo_or_cursor(qtbot):
    controller, a, child, b = make_controller(qtbot)
    session = controller.session
    session.select_card(child.id)
    editors = [CardEditorWidget(), CardEditorWidget()]
    bindings = []
    for editor in editors:
        qtbot.addWidget(editor)
        bindings.append(CardEditorBinding(session, editor, child.id))
    resets = []
    controller.window.tree_panel.tree_model.modelReset.connect(lambda: resets.append(True))
    editors[0].text_edit.insertPlainText("Hello")
    assert html_text(session.cards.get(child.id).content).strip() == "Hello"
    assert editors[1].text_edit.toPlainText() == "Hello"
    assert editors[0].text_edit.textCursor().position() == 5
    assert editors[0].text_edit.document().isUndoAvailable()
    session.update_card(child.id, title="Renamed")
    editors[0].text_edit.undo()
    assert html_text(session.cards.get(child.id).content).strip() == ""
    assert editors[1].text_edit.toPlainText() == ""
    assert resets == []
    bindings[1].dispose()
    editors[0].text_edit.moveCursor(QTextCursor.MoveOperation.End)
    editors[0].text_edit.insertPlainText("Again")
    assert editors[1].text_edit.toPlainText() == ""
