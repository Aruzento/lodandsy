import pytest

from lodandsy.application.application_session import (
    ApplicationSession,
)
from lodandsy.domain.card_collection import CardCollection


def test_session_starts_without_selection() -> None:
    cards = CardCollection()

    session = ApplicationSession(cards)

    assert session.current_card_id is None
    assert session.current_card is None


def test_session_selects_card() -> None:
    cards = CardCollection()
    card = cards.create("World")

    session = ApplicationSession(cards)

    changes: list[str | None] = []

    session.current_card_changed.connect(
        changes.append
    )

    session.select_card(card.id)

    assert session.current_card_id == card.id
    assert session.current_card is card
    assert changes == [card.id]


def test_selecting_same_card_does_not_emit_again() -> None:
    cards = CardCollection()
    card = cards.create("World")

    session = ApplicationSession(cards)

    changes: list[str | None] = []

    session.current_card_changed.connect(
        changes.append
    )

    session.select_card(card.id)
    session.select_card(card.id)

    assert changes == [card.id]


def test_session_can_clear_selection() -> None:
    cards = CardCollection()
    card = cards.create("World")

    session = ApplicationSession(cards)

    changes: list[str | None] = []

    session.current_card_changed.connect(
        changes.append
    )

    session.select_card(card.id)
    session.clear_selection()

    assert session.current_card_id is None
    assert session.current_card is None

    assert changes == [
        card.id,
        None,
    ]


def test_selecting_unknown_card_is_rejected() -> None:
    cards = CardCollection()

    session = ApplicationSession(cards)

    with pytest.raises(
        ValueError,
        match="Unknown card id",
    ):
        session.select_card(
            "missing-card"
        )

    assert session.current_card_id is None