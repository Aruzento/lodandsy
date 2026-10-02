from PySide6.QtWidgets import QMessageBox

from lodandsy.domain.card import Card
from lodandsy.ui.card_tree_model import CARD_ID_ROLE
from lodandsy.ui.tree_panel import TreePanel


def test_tree_shows_card_hierarchy(qtbot) -> None:
    world = Card(title="World")
    kingdom = Card(
        title="Kingdom",
        parent_id=world.id,
    )
    city = Card(
        title="City",
        parent_id=kingdom.id,
    )

    panel = TreePanel()
    qtbot.addWidget(panel)

    panel.set_cards([city, world, kingdom])

    model = panel.tree_model

    world_index = model.index(0, 0)
    kingdom_index = model.index(0, 0, world_index)
    city_index = model.index(0, 0, kingdom_index)

    assert model.rowCount() == 1

    assert world_index.data() == "World"
    assert world_index.data(CARD_ID_ROLE) == world.id

    assert kingdom_index.data() == "Kingdom"
    assert kingdom_index.data(CARD_ID_ROLE) == kingdom.id

    assert city_index.data() == "City"
    assert city_index.data(CARD_ID_ROLE) == city.id


def test_tree_emits_selected_card_id(qtbot) -> None:
    world = Card(title="World")
    city = Card(
        title="City",
        parent_id=world.id,
    )

    panel = TreePanel()
    qtbot.addWidget(panel)
    panel.show()

    panel.set_cards([world, city])

    world_index = panel.tree_model.index(0, 0)
    city_index = panel.tree_model.index(0, 0, world_index)

    with qtbot.waitSignal(
        panel.card_selected,
        timeout=1000,
    ) as signal:
        panel.tree_view.setCurrentIndex(city_index)

    assert signal.args == [city.id]


def test_tree_emits_open_request(qtbot) -> None:
    card = Card(title="Card")

    panel = TreePanel()
    qtbot.addWidget(panel)

    panel.set_cards([card])

    card_index = panel.tree_model.index(0, 0)

    with qtbot.waitSignal(
        panel.card_open_requested,
        timeout=1000,
    ) as signal:
        panel.tree_view.doubleClicked.emit(card_index)

    assert signal.args == [card.id]


def test_parent_card_can_be_deleted(
    qtbot,
    monkeypatch,
) -> None:
    world = Card(title="World")

    city = Card(
        title="City",
        parent_id=world.id,
    )

    panel = TreePanel()
    qtbot.addWidget(panel)

    panel.set_cards([
        world,
        city,
    ])

    world_index = panel.tree_model.index(
        0,
        0,
    )

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: (
            QMessageBox.StandardButton.Yes
        ),
    )

    with qtbot.waitSignal(
        panel.delete_requested,
        timeout=1000,
    ) as signal:
        panel.request_delete(
            world_index
        )

    assert signal.args == [world.id]