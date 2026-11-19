from lodandsy.application.app_controller import AppController
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.card_tree_model import CARD_ID_ROLE


def test_tree_editor_inspector_share_one_card_state(qtbot):
    cards = CardCollection()
    world = cards.create("World")
    kingdom = cards.create("Kingdom", world.id)
    city = cards.create("City", kingdom.id)
    cards.update_content(city.id, "# Original")
    window = AppShell()
    qtbot.addWidget(window)
    controller = AppController(window, cards)
    panel = window.tree_panel
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_card(city.id))
    window.tree_panel.request_open(panel.tree_model.index_for_card(city.id))
    editor = controller.card_editors[city.id]
    assert controller.session.current_card is cards.get(city.id)
    assert editor.text_edit.toPlainText() == "# Original"
    assert window.inspector_panel.id_edit.text() == city.id
    editor.text_edit.setPlainText("# Changed")
    window.inspector_panel.title_edit.setText("Capital")
    window.inspector_panel.title_edit.editingFinished.emit()
    assert cards.get(city.id).title == "Capital"
    assert panel.tree_model.index_for_card(city.id).data() == "Capital"
    window.inspector_panel.parent_combo.setCurrentIndex(
        window.inspector_panel.parent_combo.findData(world.id)
    )
    assert cards.get(city.id).parent_id == world.id
    assert panel.tree_model.index_for_card(city.id).parent().data(CARD_ID_ROLE) == world.id
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_card(world.id))
    assert controller.session.current_card_id == world.id
    assert window.inspector_panel.id_edit.text() == world.id
    assert editor.card_id == city.id
    assert editor.text_edit.toPlainText() == "# Changed"
    controller.open_card_editor(world.id)
    world_editor = controller.card_editors[world.id]
    world_editor.text_edit.setPlainText("# World")
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_card(city.id))
    assert cards.get(city.id).content == "# Changed"
    assert cards.get(world.id).content == "# World"
    assert editor.text_edit.toPlainText() == "# Changed"
    assert world_editor.text_edit.toPlainText() == "# World"
    assert window.inspector_panel.title_edit.text() == "Capital"
