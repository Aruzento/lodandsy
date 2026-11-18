import pytest
from PySide6.QtGui import QTextCursor

from lodandsy.application.app_controller import AppController
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.app_shell import AppShell


def make_controller(qtbot):
    cards = CardCollection()
    a, b = cards.create("A"), cards.create("B")
    cards.update_content(a.id, "A content")
    cards.update_content(b.id, "B content")
    window = AppShell()
    qtbot.addWidget(window)
    controller = AppController(window, cards)
    window.show()
    return controller, a, b


def test_tree_open_request_opens_managed_card_editor(qtbot):
    controller, a, b = make_controller(qtbot)
    controller.window.tree_panel.card_open_requested.emit(a.id)
    dock = controller.window_manager.find_window(controller.card_editor_window_key(a.id))
    assert dock.widget() is controller.card_editors[a.id]
    assert dock.widget().card_id == a.id
    assert dock.widget().text_edit.toPlainText() == "A content"
    assert controller.session.current_card_id == a.id
    assert controller.window_manager.active_window_key == dock.key
    assert dock.dock.dockAreaWidget() is not None
    assert controller.window.workspace.dockAreaCount() == 1


def test_opening_another_card_creates_independent_document_and_same_id_reuses(qtbot):
    controller, a, b = make_controller(qtbot)
    first = controller.open_card_editor(a.id)
    second = controller.open_card_editor(b.id)
    assert first is not second
    assert len(controller.window_manager.window_keys()) == 2
    assert first.widget().card_id == a.id
    assert second.widget().card_id == b.id
    first.widget().text_edit.insertPlainText("Edited ")
    assert controller.cards.get(a.id).content == "Edited A content"
    assert second.widget().text_edit.toPlainText() == "B content"
    assert controller.open_card_editor(a.id) is first
    assert len(controller.card_editors) == 2
    assert controller.window_manager.active_window_key == first.key


def test_tree_selection_and_clear_leave_open_documents_unchanged(qtbot):
    controller, a, b = make_controller(qtbot)
    dock = controller.open_card_editor(a.id)
    controller.session.select_card(b.id)
    assert dock.widget().card_id == a.id
    assert controller.window.inspector_panel.id_edit.text() == b.id
    controller.session.clear_selection()
    assert dock.widget().card_id == a.id
    assert dock.widget().text_edit.toPlainText() == "A content"
    assert controller.window.inspector_panel.id_edit.text() == ""


def test_close_reopen_preserves_document_undo_redo_and_cursor(qtbot):
    controller, a, b = make_controller(qtbot)
    dock = controller.open_card_editor(a.id)
    editor = dock.widget()
    binding = controller.card_editor_bindings[a.id]
    editor.text_edit.moveCursor(QTextCursor.MoveOperation.End)
    editor.text_edit.insertPlainText(" changed")
    cursor = editor.text_edit.textCursor()
    cursor.setPosition(2)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
    editor.text_edit.setTextCursor(cursor)
    document = editor.text_edit.document()
    assert controller.window_manager.close_window(dock.key)
    assert binding.is_disposed
    assert a.id not in controller.card_editors
    qtbot.wait(10)
    new_dock = controller.open_card_editor(a.id)
    editor = new_dock.widget()
    assert new_dock is not dock
    assert editor.text_edit.document() is document
    assert editor.text_edit.textCursor().position() == 5
    assert editor.text_edit.textCursor().anchor() == 2
    editor.text_edit.undo()
    assert controller.cards.get(a.id).content == "A content"
    editor.text_edit.redo()
    assert controller.cards.get(a.id).content == "A content changed"


def test_close_reopen_preserves_scroll(qtbot):
    controller, a, b = make_controller(qtbot)
    controller.session.update_card(a.id, content="\n".join(str(i) for i in range(500)))
    dock = controller.open_card_editor(a.id)
    qtbot.wait(20)
    bar = dock.widget().text_edit.verticalScrollBar()
    bar.setValue(100)
    value = bar.value()
    assert value > 0
    dock.close()
    qtbot.wait(10)
    reopened = controller.open_card_editor(a.id)
    qtbot.wait(20)
    assert reopened.widget().text_edit.verticalScrollBar().value() == value


def test_rename_updates_document_title_without_touching_undo(qtbot):
    controller, a, b = make_controller(qtbot)
    dock = controller.open_card_editor(a.id)
    dock.widget().text_edit.insertPlainText("Edit ")
    controller.rename_card(a.id, "New title")
    assert dock.windowTitle() == "New title"
    dock.widget().text_edit.undo()
    assert controller.cards.get(a.id).content == "A content"


def test_subtree_delete_closes_only_deleted_documents_and_drops_their_state(qtbot):
    controller, a, b = make_controller(qtbot)
    child = controller.create_card("Child", a.id)
    for card_id in [a.id, child.id, b.id]:
        controller.open_card_editor(card_id)
    survivor = controller.card_editors[b.id]
    survivor.text_edit.insertPlainText("Keep ")
    controller.delete_card(a.id)
    assert set(controller.card_editors) == {b.id}
    assert set(controller.card_document_states) == {b.id}
    assert survivor.text_edit.toPlainText() == "Keep B content"
    assert controller.session.current_card_id == b.id
    survivor.text_edit.undo()
    assert controller.cards.get(b.id).content == "B content"


def test_failed_window_open_disposes_binding_and_can_retry(qtbot, monkeypatch):
    controller, a, b = make_controller(qtbot)
    original = controller.window.workspace.add_document
    def fail(*args):
        raise RuntimeError("Simulated placement failure")
    monkeypatch.setattr(controller.window.workspace, "add_document", fail)
    with pytest.raises(RuntimeError, match="placement failure"):
        controller.open_card_editor(a.id)
    assert a.id not in controller.card_editors
    assert a.id not in controller.card_editor_bindings
    assert controller.window_manager.window_keys() == ()
    monkeypatch.setattr(controller.window.workspace, "add_document", original)
    assert controller.open_card_editor(a.id).widget().card_id == a.id


def test_external_content_update_while_closed_is_kept_on_reopen(qtbot):
    controller, a, b = make_controller(qtbot)
    controller.open_card_editor(a.id).close()
    qtbot.wait(10)
    controller.session.update_card(a.id, content="External")
    dock = controller.open_card_editor(a.id)
    assert dock.widget().text_edit.toPlainText() == "External"
    dock.widget().text_edit.undo()
    assert controller.cards.get(a.id).content == "A content"
