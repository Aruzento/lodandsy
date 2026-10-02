from PySide6.QtCore import QModelIndex, Qt

from lodandsy.domain.card import Card
from lodandsy.ui.card_tree_model import CardTreeModel


def test_drop_requests_reparent(qtbot) -> None:
    world = Card(title="World")

    kingdom = Card(
        title="Kingdom",
        parent_id=world.id,
    )
    city = Card(
        title="City",
        parent_id=world.id,
    )

    model = CardTreeModel()
    model.set_cards([world, kingdom, city])

    world_index = model.index(0, 0)
    kingdom_index = model.index(
        0,
        0,
        world_index,
    )
    city_index = model.index(
        1,
        0,
        world_index,
    )

    mime_data = model.mimeData([city_index])

    with qtbot.waitSignal(
        model.reparent_requested,
        timeout=1000,
    ) as signal:
        handled = model.dropMimeData(
            mime_data,
            Qt.DropAction.MoveAction,
            -1,
            -1,
            kingdom_index,
        )

    assert handled
    assert signal.args == [
        city.id,
        kingdom.id,
    ]


def test_drop_on_root_requests_root_parent(
    qtbot,
) -> None:
    world = Card(title="World")

    city = Card(
        title="City",
        parent_id=world.id,
    )

    model = CardTreeModel()
    model.set_cards([world, city])

    world_index = model.index(0, 0)
    city_index = model.index(
        0,
        0,
        world_index,
    )

    mime_data = model.mimeData([city_index])

    with qtbot.waitSignal(
        model.reparent_requested,
        timeout=1000,
    ) as signal:
        handled = model.dropMimeData(
            mime_data,
            Qt.DropAction.MoveAction,
            -1,
            -1,
            QModelIndex(),
        )

    assert handled
    assert signal.args == [
        city.id,
        None,
    ]


def test_drop_between_rows_is_rejected() -> None:
    first = Card(title="First")
    second = Card(title="Second")

    model = CardTreeModel()
    model.set_cards([first, second])

    first_index = model.index(0, 0)
    mime_data = model.mimeData([first_index])

    assert not model.canDropMimeData(
        mime_data,
        Qt.DropAction.MoveAction,
        1,
        0,
        QModelIndex(),
    )


def test_drop_into_descendant_is_rejected() -> None:
    world = Card(title="World")

    kingdom = Card(
        title="Kingdom",
        parent_id=world.id,
    )
    city = Card(
        title="City",
        parent_id=kingdom.id,
    )

    model = CardTreeModel()
    model.set_cards([world, kingdom, city])

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

    mime_data = model.mimeData([world_index])

    assert not model.canDropMimeData(
        mime_data,
        Qt.DropAction.MoveAction,
        -1,
        -1,
        city_index,
    )