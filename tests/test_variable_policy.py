import json
from dataclasses import replace

import pytest

from lodandsy.application.card_payload_codec import decode_card, encode_card
from lodandsy.application.cards_service import CardsService
from lodandsy.domain.card import Card, CardPayload
from lodandsy.domain.card_schema import CARD_TYPES, parse_field


def test_availability_is_enforced_at_every_card_boundary(qapp):
    card = Card("Note")
    service = CardsService()
    saved = service.create_card("Note")
    for operation in (
        lambda: Card("Note", values=(("hp_max", 20),)),
        lambda: card.with_fields({"hp_max": 20}),
        lambda: CardPayload(card.sections, values=(("hp_max", 20),)),
        lambda: service.update_card_fields(saved.id, {"summary": "partial", "hp_max": 20}),
        lambda: service.entities.put_payload(
            saved.id, replace(saved.payload(), values=(("hp_max", 20),))
        ),
    ):
        with pytest.raises(ValueError):
            operation()
    assert service.get_card(saved.id) == saved
    version, source = encode_card(card)
    data = json.loads(source)
    data["fields"]["hp_max"] = 20
    with pytest.raises(ValueError):
        decode_card(card.title, card.id, None, version, json.dumps(data))
    assert len(CARD_TYPES) == 12


def test_resource_types_scope_presence_and_no_legacy():
    card = Card("Actor", card_type="character")
    assert card.value("strength") == 10
    assert "strength" not in dict(card.values)
    assert card.with_fields({"hp_max": 0, "player": False}).value("hp_max") == 0
    for changes in (
        {"hp_max": 1.5},
        {"hp_max": True},
        {"hp_current": 1},
        {"player": None},
        {"hp": 20},
        {"strength": float("nan")},
    ):
        with pytest.raises(ValueError):
            card.with_fields(changes)
    assert parse_field("hp_gains", "10,6,6") == (10, 6, 6)
    assert parse_field("player", "false") is False
