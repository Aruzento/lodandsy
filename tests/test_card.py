from lodandsy.domain.card import Card


def test_card_has_default_state() -> None:
    card = Card(title="First card")

    assert card.id
    assert card.title == "First card"
    assert card.parent_id is None
    assert card.content == ""


def test_card_can_be_changed() -> None:
    card = Card(title="Old title")

    card.title = "New title"
    card.content = "Some content"
    card.parent_id = "parent-1"

    assert card.title == "New title"
    assert card.content == "Some content"
    assert card.parent_id == "parent-1"


def test_cards_get_different_ids() -> None:
    first = Card(title="First")
    second = Card(title="Second")

    assert first.id != second.id