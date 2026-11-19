from lodandsy.application.app_controller import AppController
from lodandsy.application.card_editor_binding import (
    CardEditorBinding,
)
from lodandsy.application.rich_html import text_document
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.card_editor import CardEditorWidget


def test_tree_selection_updates_session(
    qtbot,
) -> None:
    cards = CardCollection()

    world = cards.create("World")

    city = cards.create(
        "City",
        parent_id=world.id,
    )

    window = AppShell()
    qtbot.addWidget(window)

    controller = AppController(
        window,
        cards,
    )

    model = window.tree_panel.tree_model

    world_index = model.index_for_node("card:" + world.id)

    city_index = model.index(
        0,
        0,
        world_index,
    )

    with qtbot.waitSignal(
        controller.cards_service.current_card_changed,
        timeout=1000,
    ) as signal:
        window.tree_panel.tree_view.setCurrentIndex(city_index)

    assert signal.args == [city.id]

    assert controller.cards_service.current_card_id == city.id

    assert controller.cards_service.current_card is city


def test_tree_can_switch_session_selection(
    qtbot,
) -> None:
    cards = CardCollection()

    world = cards.create("World")

    city = cards.create(
        "City",
        parent_id=world.id,
    )

    window = AppShell()
    qtbot.addWidget(window)

    controller = AppController(
        window,
        cards,
    )

    model = window.tree_panel.tree_model

    world_index = model.index_for_node("card:" + world.id)

    city_index = model.index(
        0,
        0,
        world_index,
    )

    window.tree_panel.tree_view.setCurrentIndex(world_index)

    assert controller.cards_service.current_card_id == world.id

    window.tree_panel.tree_view.setCurrentIndex(city_index)

    assert controller.cards_service.current_card_id == city.id


def test_tree_selection_updates_editor_and_inspector(
    qtbot,
) -> None:
    cards = CardCollection()

    world = cards.create("World")
    world = cards.update(world.id, content=text_document("# World"))

    city = cards.create(
        "City",
        parent_id=world.id,
    )
    city = cards.update(city.id, content=text_document("# City"))

    window = AppShell()
    qtbot.addWidget(window)

    controller = AppController(
        window,
        cards,
    )

    editor = CardEditorWidget()
    qtbot.addWidget(editor)

    editor_binding = CardEditorBinding(
        controller.cards_service,
        editor,
        city.id,
    )

    model = window.tree_panel.tree_model

    world_index = model.index_for_node("card:" + world.id)

    city_index = model.index(
        0,
        0,
        world_index,
    )

    window.tree_panel.tree_view.setCurrentIndex(city_index)

    assert controller.cards_service.current_card_id == city.id

    assert editor.card_id == city.id
    assert editor.text_edit.toPlainText() == "# City"

    assert window.inspector_panel.id_edit.text() == city.id

    assert window.inspector_panel.title_edit.text() == "City"

    assert editor_binding.session is controller.cards_service


def test_deleting_selected_card_clears_session_and_views(
    qtbot,
) -> None:
    cards = CardCollection()

    world = cards.create("World")

    city = cards.create(
        "City",
        parent_id=world.id,
    )
    city = cards.update(city.id, content=text_document("# City"))

    window = AppShell()
    qtbot.addWidget(window)

    controller = AppController(
        window,
        cards,
    )

    editor = CardEditorWidget()
    qtbot.addWidget(editor)

    editor_binding = CardEditorBinding(
        controller.cards_service,
        editor,
        city.id,
    )

    model = window.tree_panel.tree_model

    world_index = model.index_for_node("card:" + world.id)

    city_index = model.index(
        0,
        0,
        world_index,
    )

    window.tree_panel.tree_view.setCurrentIndex(city_index)

    assert controller.cards_service.current_card_id == city.id

    controller.delete_card(city.id)

    assert controller.cards_service.current_card_id is None
    assert controller.cards_service.current_card is None

    assert editor.card_id is None
    assert not editor.text_edit.isEnabled()

    assert window.inspector_panel.id_edit.text() == ""
    assert not window.inspector_panel.title_edit.isEnabled()

    assert editor_binding.session is controller.cards_service
