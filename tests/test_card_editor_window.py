from lodandsy.application.app_controller import (
    AppController,
)
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.card_editor import CardEditorWidget


def _make_controller(
    qtbot,
) -> tuple[
    AppShell,
    AppController,
    CardCollection,
]:
    cards = CardCollection()

    world = cards.create(
        "World"
    )
    world.content = (
        "# World\n\nWorld content."
    )

    city = cards.create(
        "City",
        parent_id=world.id,
    )
    city.content = (
        "# City\n\nCity content."
    )

    window = AppShell()

    qtbot.addWidget(
        window
    )

    controller = AppController(
        window,
        cards,
    )

    window.show()

    return (
        window,
        controller,
        cards,
    )


def test_tree_open_request_opens_managed_card_editor(
    qtbot,
) -> None:
    window, controller, cards = (
        _make_controller(
            qtbot
        )
    )

    card = next(
        card
        for card in cards.all()
        if card.title == "City"
    )

    window.tree_panel.card_open_requested.emit(
        card.id
    )

    dock = (
        controller.window_manager.find_window(
            controller.CARD_EDITOR_WINDOW_KEY
        )
    )

    assert dock is not None

    assert (
        controller.session.current_card_id
        == card.id
    )

    editor = dock.widget()

    assert isinstance(
        editor,
        CardEditorWidget,
    )

    assert (
        editor
        is controller.card_editor_widget
    )

    assert (
        editor.card_id
        == card.id
    )

    assert (
        editor.text_edit.toPlainText()
        == "# City\n\nCity content."
    )

    assert window.is_workspace_dock_centered(
        dock
    )


def test_opening_another_card_reuses_same_editor_window(
    qtbot,
) -> None:
    _window, controller, cards = (
        _make_controller(
            qtbot
        )
    )

    world = next(
        card
        for card in cards.all()
        if card.title == "World"
    )

    city = next(
        card
        for card in cards.all()
        if card.title == "City"
    )

    first_dock = controller.open_card_editor(
        world.id
    )

    first_editor = (
        controller.card_editor_widget
    )

    second_dock = controller.open_card_editor(
        city.id
    )

    assert second_dock is first_dock

    assert (
        controller.card_editor_widget
        is first_editor
    )

    assert (
        controller.window_manager.window_keys()
        == (
            controller.CARD_EDITOR_WINDOW_KEY,
        )
    )

    assert (
        controller.session.current_card_id
        == city.id
    )

    assert first_editor is not None

    assert (
        first_editor.card_id
        == city.id
    )

    assert (
        first_editor.text_edit.toPlainText()
        == "# City\n\nCity content."
    )


def test_managed_card_editor_updates_card_collection(
    qtbot,
) -> None:
    _window, controller, cards = (
        _make_controller(
            qtbot
        )
    )

    city = next(
        card
        for card in cards.all()
        if card.title == "City"
    )

    controller.open_card_editor(
        city.id
    )

    editor = controller.card_editor_widget

    assert editor is not None

    editor.text_edit.setPlainText(
        "# City\n\nChanged through managed editor."
    )

    assert (
        cards.get(city.id).content
        == "# City\n\nChanged through managed editor."
    )


def test_tree_selection_updates_open_editor(
    qtbot,
) -> None:
    _window, controller, cards = (
        _make_controller(
            qtbot
        )
    )

    world = next(
        card
        for card in cards.all()
        if card.title == "World"
    )

    city = next(
        card
        for card in cards.all()
        if card.title == "City"
    )

    controller.open_card_editor(
        city.id
    )

    editor = controller.card_editor_widget

    assert editor is not None

    controller.session.select_card(
        world.id
    )

    assert (
        editor.card_id
        == world.id
    )

    assert (
        editor.text_edit.toPlainText()
        == "# World\n\nWorld content."
    )


def test_closing_editor_disposes_binding_and_reopen_works(
    qtbot,
) -> None:
    _window, controller, cards = (
        _make_controller(
            qtbot
        )
    )

    world = next(
        card
        for card in cards.all()
        if card.title == "World"
    )

    city = next(
        card
        for card in cards.all()
        if card.title == "City"
    )

    first_dock = controller.open_card_editor(
        city.id
    )

    first_editor = (
        controller.card_editor_widget
    )
    first_binding = (
        controller.card_editor_binding
    )

    assert first_editor is not None
    assert first_binding is not None

    assert (
        controller.window_manager.close_window(
            controller.CARD_EDITOR_WINDOW_KEY
        )
    )

    assert first_binding.is_disposed

    assert (
        controller.card_editor_widget
        is None
    )

    assert (
        controller.card_editor_binding
        is None
    )

    assert (
        controller.window_manager.find_window(
            controller.CARD_EDITOR_WINDOW_KEY
        )
        is None
    )

    # После закрытия старый binding уже не должен
    # получать session callbacks.
    controller.session.select_card(
        world.id
    )

    qtbot.wait(
        10
    )

    second_dock = controller.open_card_editor(
        world.id
    )

    second_editor = (
        controller.card_editor_widget
    )

    assert second_dock is not first_dock

    assert second_editor is not None
    assert second_editor is not first_editor

    assert (
        second_editor.card_id
        == world.id
    )

    assert (
        second_editor.text_edit.toPlainText()
        == "# World\n\nWorld content."
    )