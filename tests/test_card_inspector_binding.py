from lodandsy.application.app_controller import AppController
from lodandsy.application.application_session import (
    ApplicationSession,
)
from lodandsy.application.card_inspector_binding import (
    CardInspectorBinding,
)
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.inspector_panel import InspectorPanel


def test_binding_loads_card_and_filters_invalid_parents(
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
        parent_id=kingdom.id,
    )

    characters = cards.create(
        "Characters"
    )

    session = ApplicationSession(cards)

    inspector = InspectorPanel()
    qtbot.addWidget(inspector)

    binding = CardInspectorBinding(
        session,
        inspector,
    )

    session.select_card(
        kingdom.id
    )

    assert inspector.id_edit.text() == kingdom.id
    assert inspector.title_edit.text() == "Kingdom"

    option_ids = [
        inspector.parent_combo.itemData(index)
        for index in range(
            inspector.parent_combo.count()
        )
    ]

    assert None in option_ids
    assert world.id in option_ids
    assert characters.id in option_ids

    assert kingdom.id not in option_ids
    assert city.id not in option_ids

    assert (
        inspector.parent_combo.currentData()
        == world.id
    )

    assert binding.session is session


def test_binding_updates_title(
    qtbot,
) -> None:
    cards = CardCollection()
    card = cards.create("Old title")

    session = ApplicationSession(cards)

    inspector = InspectorPanel()
    qtbot.addWidget(inspector)

    changed = 0

    def on_changed() -> None:
        nonlocal changed
        changed += 1

    binding = CardInspectorBinding(
        session,
        inspector,
        on_cards_changed=on_changed,
    )

    session.select_card(card.id)

    inspector.title_edit.setText(
        "New title"
    )
    inspector.title_edit.editingFinished.emit()

    assert cards.get(card.id).title == "New title"
    assert changed == 1
    assert binding.session is session


def test_binding_updates_parent(
    qtbot,
) -> None:
    cards = CardCollection()

    world = cards.create("World")
    city = cards.create("City")

    session = ApplicationSession(cards)

    inspector = InspectorPanel()
    qtbot.addWidget(inspector)

    binding = CardInspectorBinding(
        session,
        inspector,
    )

    session.select_card(city.id)

    world_index = next(
        index
        for index in range(
            inspector.parent_combo.count()
        )
        if (
            inspector.parent_combo.itemData(index)
            == world.id
        )
    )

    inspector.parent_combo.setCurrentIndex(
        world_index
    )

    assert (
        cards.get(city.id).parent_id
        == world.id
    )

    assert binding.session is session


def test_inspector_changes_refresh_tree(
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

    controller.session.select_card(
        city.id
    )

    window.inspector_panel.title_edit.setText(
        "Capital"
    )
    window.inspector_panel.title_edit.editingFinished.emit()

    assert cards.get(city.id).title == "Capital"

    model = window.tree_panel.tree_model

    world_index = model.index(0, 0)

    city_index = model.index(
        0,
        0,
        world_index,
    )

    assert city_index.data() == "Capital"

    root_index = next(
        index
        for index in range(
            window.inspector_panel.parent_combo.count()
        )
        if (
            window.inspector_panel.parent_combo.itemData(
                index
            )
            is None
        )
    )

    window.inspector_panel.parent_combo.setCurrentIndex(
        root_index
    )

    assert cards.get(city.id).parent_id is None

    assert model.rowCount() == 2