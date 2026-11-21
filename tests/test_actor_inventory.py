import pytest

from lodandsy.domain.modifiers import Modifier

pytest_plugins = ["tests.project_fixture"]


def test_inventory_clone_activation_live_modifiers_and_isolation(project):
    app, _ = project
    cards, tables = app.cards_service, app.tables_service
    card = app.create_card("Воин", card_type="character")
    cards.update_card_fields(
        card.id,
        {
            "level": 5,
            "hit_die": 10,
            "hp_gains": (10, 6, 6, 6, 6),
            "constitution": 14,
            "hp_max_mode": "auto",
        },
    )
    section = next(s for s in card.sections if s.purpose == "inventory")
    template = app.actions.section_table(card.id, section.id)
    item = app.create_card("Амулет", card_type="item")
    cards.update_card_fields(
        item.id,
        {
            "weight": 2,
            "cost": 0,
            "modifiers": (Modifier("constitution", operand=2),),
        },
    )
    tables.edit_table(template.id, rows=(template.new_row(),))
    template = tables.get_table(template.id)
    tables.set_cell(template.id, template.rows[0].id, template.columns[0].id, item.id)
    first, second = cards.create_actor(card.id), cards.create_actor(card.id)
    a, b = cards.get_actor(first), cards.get_actor(second)
    assert a.inventory_id != b.inventory_id != template.id
    inv_a, inv_b = tables.get_table(a.inventory_id), tables.get_table(b.inventory_id)
    assert inv_a.rows[0].id != inv_b.rows[0].id != template.rows[0].id
    assert cards.effective(first).get("hp_max").value == 44
    active = next(c for c in inv_a.columns if c.key == "active")
    quantity = next(c for c in inv_a.columns if c.key == "quantity")
    tables.set_cell(inv_a.id, inv_a.rows[0].id, active.id, True, parsed=True)
    assert cards.effective(first).get("hp_max").value == 49
    assert cards.effective(second).get("hp_max").value == 44
    tables.set_cell(inv_a.id, inv_a.rows[0].id, quantity.id, "8")
    assert cards.effective(first).get("hp_max").value == 49
    cards.update_actor(first, {"hp_current": 49})
    tables.set_cell(inv_a.id, inv_a.rows[0].id, active.id, False, parsed=True)
    assert cards.get_actor(first).value("hp_current") == 44
    tables.set_cell(inv_a.id, inv_a.rows[0].id, active.id, True, parsed=True)
    app.actions.delete_entity(item.id)
    assert tables.get_table(inv_a.id).rows[0].value(inv_a.columns[0].id) == item.id
    assert cards.effective(first).get("hp_max").status == "incomplete"
    assert cards.effective(second).get("hp_max").value == 44


def test_object_inventory_and_explicit_delete_owner(project):
    app, _ = project
    card = app.create_card("Сундук", card_type="object")
    first, second = app.cards_service.create_actor(card.id), app.cards_service.create_actor(card.id)
    a = app.cards_service.get_actor(first)
    b = app.cards_service.get_actor(second)
    assert a.inventory_id != b.inventory_id
    assert app.tables_service.get_table(a.inventory_id).rows == ()
    with pytest.raises(ValueError):
        app.actions.delete_entity(a.inventory_id)
    with pytest.raises(ValueError):
        app.actions.delete_actor(first)
    app.actions.delete_actor(first, confirmed=True)
    assert app.cards_service.list_actors(card.id) == (b,)
    with pytest.raises(ValueError):
        app.tables_service.get_table(a.inventory_id)


def test_actor_delete_retires_only_its_addressed_drafts(project):
    from lodandsy.domain.actor_state import ValueAddress

    app, _ = project
    card = app.create_card("NPC", card_type="creature")
    first, second = [app.cards_service.create_actor(card.id) for _ in range(2)]
    edits = app.cards_service.field_edits
    addresses = [ValueAddress(card.id, "hp_current", ref.actor_id) for ref in (first, second)]
    owners = [edits.begin(address) for address in addresses]
    for owner in owners:
        edits.text(owner, "invalid")
        assert not edits.commit(owner)
    app.actions.delete_actor(first, confirmed=True)
    assert not edits.has(owners[0])
    assert edits.has(owners[1])
    assert addresses[0] not in edits.drafts
    assert addresses[1] in edits.drafts
