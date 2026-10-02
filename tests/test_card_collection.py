import pytest

from lodandsy.domain.card_collection import CardCollection


def test_create_card() -> None:
    cards = CardCollection()

    world = cards.create("World")
    city = cards.create(
        "City",
        parent_id=world.id,
    )

    assert cards.get(world.id) is world
    assert city.parent_id == world.id


def test_rename_card() -> None:
    cards = CardCollection()
    card = cards.create("Old title")

    cards.rename(
        card.id,
        "New title",
    )

    assert card.title == "New title"


def test_reparent_card() -> None:
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

    cards.reparent(
        city.id,
        kingdom.id,
    )

    assert city.parent_id == kingdom.id


def test_reparent_card_to_root() -> None:
    cards = CardCollection()

    world = cards.create("World")

    city = cards.create(
        "City",
        parent_id=world.id,
    )

    cards.reparent(
        city.id,
        None,
    )

    assert city.parent_id is None


def test_reparent_rejects_self_parent() -> None:
    cards = CardCollection()
    card = cards.create("Card")

    with pytest.raises(
        ValueError,
        match="own parent",
    ):
        cards.reparent(
            card.id,
            card.id,
        )


def test_reparent_rejects_cycle() -> None:
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

    with pytest.raises(
        ValueError,
        match="cycle",
    ):
        cards.reparent(
            world.id,
            city.id,
        )


def test_reparent_rejects_unknown_parent() -> None:
    cards = CardCollection()
    card = cards.create("Card")

    with pytest.raises(
        ValueError,
        match="Unknown card id",
    ):
        cards.reparent(
            card.id,
            "missing-parent",
        )


def test_delete_leaf_card() -> None:
    cards = CardCollection()
    card = cards.create("Card")

    deleted_ids = cards.delete(card.id)

    assert deleted_ids == (card.id,)
    assert cards.all() == ()


def test_delete_removes_entire_subtree() -> None:
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

    tavern = cards.create(
        "Tavern",
        parent_id=city.id,
    )

    characters = cards.create(
        "Characters",
        parent_id=world.id,
    )

    deleted_ids = cards.delete(
        kingdom.id
    )

    assert set(deleted_ids) == {
        kingdom.id,
        city.id,
        tavern.id,
    }

    assert cards.all() == (
        world,
        characters,
    )

    assert (
        cards.get(characters.id).parent_id
        == world.id
    )


def test_delete_root_removes_all_descendants() -> None:
    cards = CardCollection()

    world = cards.create("World")

    kingdom = cards.create(
        "Kingdom",
        parent_id=world.id,
    )

    cards.create(
        "City",
        parent_id=kingdom.id,
    )

    cards.delete(world.id)

    assert cards.all() == ()

def test_update_content() -> None:
    cards = CardCollection()
    card = cards.create("Card")

    cards.update_content(
        card.id,
        "# Heading\n\nSome text",
    )

    assert card.content == "# Heading\n\nSome text"
    