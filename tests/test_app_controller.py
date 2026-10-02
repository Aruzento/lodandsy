from lodandsy.application.app_controller import AppController
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.card_tree_model import CARD_ID_ROLE


def test_reparent_request_updates_data_and_tree(
    qtbot,
) -> None:
    cards = CardCollection()

    world = cards.create("World")

    kingdom = cards.create(
        "Kingdom",
        parent_id=world.id,
    )

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

    window.tree_panel.reparent_requested.emit(
        city.id,
        kingdom.id,
    )

    assert (
        cards.get(city.id).parent_id
        == kingdom.id
    )

    model = window.tree_panel.tree_model

    world_index = model.index(0, 0)

    kingdom_index = model.index(
        0,
        0,
        world_index,
    )

    city_index = model.index(
        0,
        0,
        kingdom_index,
    )

    assert (
        city_index.data(CARD_ID_ROLE)
        == city.id
    )

    assert controller.cards is cards


def test_tree_commands_update_collection_and_tree(
    qtbot,
) -> None:
    cards = CardCollection()

    window = AppShell()
    qtbot.addWidget(window)

    controller = AppController(
        window,
        cards,
    )

    window.tree_panel.create_requested.emit(
        "World",
        None,
    )

    world = cards.all()[0]

    assert world.title == "World"
    assert world.parent_id is None

    window.tree_panel.create_requested.emit(
        "City",
        world.id,
    )

    city = next(
        card
        for card in cards.all()
        if card.title == "City"
    )

    assert city.parent_id == world.id

    model = window.tree_panel.tree_model

    world_index = model.index(0, 0)
    city_index = model.index(
        0,
        0,
        world_index,
    )

    assert city_index.data() == "City"
    assert (
        city_index.data(CARD_ID_ROLE)
        == city.id
    )

    window.tree_panel.rename_requested.emit(
        city.id,
        "Capital",
    )

    assert cards.get(city.id).title == "Capital"

    world_index = model.index(0, 0)
    city_index = model.index(
        0,
        0,
        world_index,
    )

    assert city_index.data() == "Capital"

    window.tree_panel.delete_requested.emit(
        city.id
    )

    assert cards.all() == (world,)

    world_index = model.index(0, 0)

    assert model.rowCount(world_index) == 0
    assert controller.cards is cards