from lodandsy.application.app_controller import AppController
from lodandsy.application.rich_html import html_text, text_document
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.project_tree_model import NODE_ID_ROLE


def test_tree_editor_inspector_share_one_card_state(qtbot):
    cards = CardCollection()
    world = cards.create("World")
    kingdom = cards.create("Kingdom", world.id)
    city = cards.create("City", kingdom.id)
    cards.update_content(city.id, text_document("# Original"))
    window = AppShell()
    qtbot.addWidget(window)
    controller = AppController(window, cards)
    panel = window.tree_panel
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_node("card:" + city.id))
    window.tree_panel.request_open(panel.tree_model.index_for_node("card:" + city.id))
    editor = controller.card_views.editors[city.id]
    assert controller.cards_service.current_card is cards.get(city.id)
    assert editor.text_edit.toPlainText() == "# Original"
    assert window.inspector_panel.id_edit.text() == city.id
    editor.text_edit.setPlainText("# Changed")
    window.inspector_panel.title_edit.setText("Capital")
    window.inspector_panel.title_edit.editingFinished.emit()
    assert cards.get(city.id).title == "Capital"
    assert panel.tree_model.index_for_node("card:" + city.id).data() == "Capital"
    window.inspector_panel.parent_combo.setCurrentIndex(
        window.inspector_panel.parent_combo.findData(world.id)
    )
    assert cards.get(city.id).parent_id == world.id
    assert (
        panel.tree_model.index_for_node("card:" + city.id).parent().data(NODE_ID_ROLE) == world.id
    )
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_node("card:" + world.id))
    assert controller.cards_service.current_card_id == world.id
    assert window.inspector_panel.id_edit.text() == world.id
    assert editor.card_id == city.id
    assert editor.text_edit.toPlainText() == "# Changed"
    controller.open_card_editor(world.id)
    world_editor = controller.card_views.editors[world.id]
    world_editor.text_edit.setPlainText("# World")
    world_editor.flush_pending()
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_node("card:" + city.id))
    assert html_text(cards.get(city.id).content).strip() == "# Changed"
    assert html_text(cards.get(world.id).content).strip() == "# World"
    assert editor.text_edit.toPlainText() == "# Changed"
    assert world_editor.text_edit.toPlainText() == "# World"
    assert window.inspector_panel.title_edit.text() == "Capital"
