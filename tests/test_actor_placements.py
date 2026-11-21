from dataclasses import replace

from lodandsy.domain.actor_state import ActorRef

pytest_plugins = ["tests.project_fixture"]


def test_npc_copy_player_reuse_and_undo_guards(project):
    app, _ = project
    cards, maps = app.cards_service, app.maps_service
    card = app.create_card("Гоблин", card_type="creature")
    cards.update_card_fields(card.id, {"hp_max": 20})
    first_map = maps.create_map("A", card.id)
    second_map = maps.create_map("B", card.id)
    first = maps.add_token(first_map.id, card.id, 1, 2)
    ref = ActorRef(card.id, first.actor_id)
    cards.update_actor(ref, {"hp_current": 7})
    copied = app.actions.copy_token(first_map.id, first.id)
    copy_ref = ActorRef(card.id, copied.actor_id)
    assert copied.actor_id != first.actor_id
    assert cards.get_actor(copy_ref).value("hp_current") == 20
    stack = maps.undo_stack(first_map.id)
    assert stack.undo()
    assert len(cards.list_actors(card.id)) == 1
    assert stack.redo()
    assert maps.get_map(first_map.id).tokens[-1] == copied
    cards.update_actor(copy_ref, {"hp_current": 19})
    index = stack.index()
    assert not stack.undo() and stack.index() == index
    assert cards.get_actor(copy_ref).value("hp_current") == 19
    cards.set_player(card.id, True, actor_id=first.actor_id)
    player = maps.add_token(second_map.id, card.id, 10, 10)
    another = app.actions.copy_token(second_map.id, player.id)
    assert player.actor_id == another.actor_id == first.actor_id
    cards.update_actor(ref, {"hp_current": 5})
    maps.move_token(second_map.id, player.id, 20, 30)
    cards.update_actor(ref, {"hp_current": 4})
    assert maps.undo_stack(second_map.id).undo()
    assert cards.get_actor(ref).value("hp_current") == 4
    assert maps.get_map(second_map.id).tokens[0].x == 10
    maps.delete_token(second_map.id, player.id)
    assert cards.get_actor(ref).value("hp_current") == 4


def test_map_delta_does_not_resurrect_other_placements(project):
    app, _ = project
    cards, maps = app.cards_service, app.maps_service
    card = app.create_card("NPC", card_type="object")
    document = maps.create_map("A", card.id)
    token = maps.add_token(document.id, card.id, 1, 2)
    maps.edit_map(document.id, grid=replace(document.grid, opacity=0.7))
    # Independent committed placement deletion, outside the grid command history.
    maps.commit_placements(document.id, ())
    assert maps.undo_stack(document.id).undo()
    assert maps.get_map(document.id).tokens == ()
    assert len(cards.list_actors(card.id)) == 1
    assert token.actor_id == cards.list_actors(card.id)[0].id
