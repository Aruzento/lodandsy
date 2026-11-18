from lodandsy.application.app_controller import AppController
from lodandsy.ui.app_shell import AppShell


def test_late_close_signal_does_not_dispose_reopened_document(qtbot):
    window = AppShell()
    qtbot.addWidget(window)
    controller = AppController(window)
    card = controller.create_card("Card")
    previous = controller.open_card_editor(card.id)
    previous.close()
    reopened = controller.open_card_editor(card.id)
    previous.closed.emit(previous)
    assert controller.card_editors[card.id] is reopened.widget()
    assert not controller.card_editor_bindings[card.id].is_disposed
    reopened.widget().text_edit.insertPlainText("Still bound")
    assert controller.cards.get(card.id).content == "Still bound"


def test_focus_changes_active_document_without_changing_tree_selection(qtbot):
    window = AppShell()
    qtbot.addWidget(window)
    controller = AppController(window)
    a, b = controller.create_card("A"), controller.create_card("B")
    first = controller.open_card_editor(a.id)
    second = controller.open_card_editor(b.id)
    controller.window_manager._on_focus_changed(None, first.widget().text_edit)
    assert controller.window_manager.active_window_key == first.key
    assert controller.session.current_card_id == b.id
    assert window.inspector_panel.id_edit.text() == b.id
    first.close()
    assert controller.window_manager.active_window_key is None
    assert second.widget().card_id == b.id
