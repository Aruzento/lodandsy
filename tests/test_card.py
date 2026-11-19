from dataclasses import FrozenInstanceError

import pytest

from lodandsy.domain.card import EMPTY_DOCUMENT, Card


def test_card_has_default_state() -> None:
    card = Card(title="First card")

    assert card.id
    assert card.title == "First card"
    assert card.parent_id is None
    assert card.content == EMPTY_DOCUMENT


@pytest.mark.parametrize("field", ["id", "title", "content", "parent_id"])
def test_card_cannot_be_changed_outside_collection(field) -> None:
    card = Card(title="Old title")
    with pytest.raises(FrozenInstanceError):
        setattr(card, field, "invalid")
    with pytest.raises(FrozenInstanceError):
        delattr(card, field)


@pytest.mark.parametrize("title", ["", "  \t\n", None, 123])
def test_card_rejects_invalid_title(title) -> None:
    with pytest.raises(ValueError, match="title"):
        Card(title=title)


@pytest.mark.parametrize("field", ["id", "parent_id"])
@pytest.mark.parametrize("value", ["", "not-a-uuid", 123])
def test_card_rejects_invalid_ids(field, value) -> None:
    with pytest.raises(ValueError, match="UUID"):
        Card(title="Card", **{field: value})


def test_cards_get_different_ids() -> None:
    first = Card(title="First")
    second = Card(title="Second")

    assert first.id != second.id
