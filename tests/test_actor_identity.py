from dataclasses import replace

import pytest

from lodandsy.application.cards_service import CardsService
from lodandsy.domain.actor_state import ValueAddress
from lodandsy.domain.map_document import MapDocument, MapPayload, TokenInstance


def test_actor_identity_names_shared_state_and_independent_npc(qapp):
    cards = CardsService()
    card = cards.create_card("Гоблин", card_type="creature")
    cards.update_card_fields(card.id, {"hp_max": 20})
    actors = [cards.create_actor(card.id) for _ in range(10)]
    assert len({a.actor_id for a in actors}) == 10
    assert len({cards.get_actor(a).name for a in actors}) == 10
    cards.update_actor(actors[0], {"hp_current": 7})
    assert [cards.get_actor(a).value("hp_current") for a in actors] == [7] + [20] * 9
    cards.set_player(card.id, True, actor_id=actors[0].actor_id)
    cards.set_player(card.id, False)
    assert cards.get_actor(actors[0]).value("hp_current") == 7
    assert cards.get_card(card.id).default_actor_id == actors[0].actor_id
    cards.update_card_fields(card.id, {"level": 5, "title": "Goblin"})
    assert cards.get_actor(actors[0]).name == "Гоблин №1"
    assert cards.read_value(ValueAddress(card.id, "hp_current", actors[0].actor_id)).value == 7


def test_actor_owner_and_token_refs_validate_before_publication(qapp):
    cards = CardsService()
    first = cards.create_card("A", card_type="object")
    second = cards.create_card("B", card_type="object")
    actor = cards.create_actor(first.id)
    entities = cards.entities
    with pytest.raises(ValueError):
        entities.put_payload(
            second.id, replace(second.payload(), actors=first.actors or (cards.get_actor(actor),))
        )
    before = cards.get_card(first.id)
    with pytest.raises(ValueError):
        with cards.core.transaction():
            entities.put_payload(first.id, replace(before.payload(), actors=()))
            entities.put_payload(second.id, replace(second.payload(), actors=before.actors))
    assert cards.get_card(first.id) == before
    document = MapDocument("Map", first.id)
    entities.create("map", document.title, MapPayload(document.asset_id), id=document.id)
    token = TokenInstance(first.id, 1, 2, actor_id=actor.actor_id)
    entities.put_payload(document.id, MapPayload(document.asset_id, tokens=(token,)))
    with pytest.raises(ValueError):
        entities.put_payload(
            document.id, MapPayload(document.asset_id, tokens=(replace(token, card_id=second.id),))
        )
    assert entities.payload(document.id).tokens == (token,)


def test_actor_object_unknown_zero_and_generic_scope(qapp):
    cards = CardsService()
    obj = cards.create_card("Chest", card_type="object")
    ref = cards.create_actor(obj.id)
    assert cards.get_actor(ref).value("hp_current") is None
    cards.update_card_fields(obj.id, {"hp_max": 0})
    new = cards.create_actor(obj.id)
    assert cards.get_actor(new).value("hp_current") == 0
    with pytest.raises(ValueError):
        cards.update_actor(ref, {"level": 5})
    with pytest.raises(ValueError):
        cards.set_player(obj.id, True)
