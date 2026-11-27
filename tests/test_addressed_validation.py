from contextlib import closing
from dataclasses import dataclass, replace
from shutil import copyfile

import pytest

from lodandsy.application.cards_service import CardsService
from lodandsy.application.entity_queries import EntityQueries
from lodandsy.application.entity_session import EntitySession
from lodandsy.application.maps_service import MapsService
from lodandsy.application.project_actions import ProjectActions
from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.application.tables_service import TablesService
from lodandsy.domain.actor_state import ActorRef
from lodandsy.domain.currency import CoinAmount
from lodandsy.domain.document_payloads import validate_project
from lodandsy.domain.modifiers import Modifier

pytest_plugins = ["tests.project_fixture"]


@dataclass
class World:
    core: EntitySession
    cards: CardsService
    maps: MapsService
    tables: TablesService
    actions: ProjectActions

    def records(self):
        entities = self.core.entities
        return entities.settings, tuple((e, entities.payload(e.id)) for e in entities.summaries())


def runtime(snapshot, *, complete=False):
    core = EntitySession(snapshot.entity_collection())
    cards = CardsService(core=core)
    references = EntityQueries(core, cards.reference_info)
    cards.card_changed.connect(references.refresh)
    maps, tables = MapsService(core), TablesService(core, references=references)
    actions = ProjectActions(core, cards, tables, maps)
    if complete:
        core.entities.change_validator.full_validation = True
        core.prepare = lambda changes: cards.reconcile(changes, complete=True)
    return World(core, cards, maps, tables, actions)


@pytest.fixture
def scenario(project, tmp_path):
    from tests.test_equipment import character, item, row
    from tests.test_map_tokens_grid import image_file

    app, controller = project
    assert controller.create_project(tmp_path / "world")
    asset = controller.store.import_asset(image_file(tmp_path / "board.png"))
    controller.assets[asset.id] = asset
    first_map = app.maps_service.create_map("First", asset.id)
    second_map = app.maps_service.create_map("Second", asset.id)
    first, template = character(app)
    second = app.create_card("Second user", card_type="character")
    unrelated = app.create_card("Unrelated", card_type="character")
    for card in (first, second):
        app.cards_service.update_card_fields(card.id, {
            "hp_max": 24, "hp_max_mode": "manual", "level": 1, "hit_die": 8, "hp_gains": (8,),
        })
    armor, spare = item(app), item(app, category="heavy", ac=18)
    bonus = Modifier("hp_max", operand=5)
    app.cards_service.update_card_fields(armor.id, {"modifiers": (bonus,)})
    row(app, template.id, armor, active=True)
    token = app.actions.place_card(first_map.id, first.id, 60, 80)
    other = app.actions.place_card(second_map.id, second.id, 90, 90)
    idle = app.cards_service.create_actor(unrelated.id)
    one, two = ActorRef(first.id, token.actor_id), ActorRef(second.id, other.actor_id)
    inventory = app.cards_service.get_actor(one).inventory_id
    second_inventory = app.cards_service.get_actor(two).inventory_id
    row(app, inventory, spare)
    row(app, second_inventory, armor, active=True)
    assert controller.save_current()
    return (
        controller.store.load(), one, two, idle, armor, spare, first_map, token, second_map, other,
    )


def test_addressed_transactions_match_full_reference(scenario, tmp_path):
    snapshot, one, two, idle, armor, spare, board, token, other_board, other = scenario
    worlds = (runtime(snapshot), runtime(snapshot, complete=True))
    table_id = worlds[0].cards.get_actor(one).inventory_id
    table = worlds[0].tables.get_table(table_id)
    first, extra = (entry.id for entry in table.rows)
    quantity = next(column.id for column in table.columns if column.key == "quantity")
    active = next(column.id for column in table.columns if column.key == "active")

    def reject_inventory_removal(w):
        w.core.delete(table_id)

    def duplicate_token(w):
        w.maps.edit_map(board.id, tokens=(token, other))

    def foreign_actor(w):
        w.maps.edit_map(board.id, tokens=(replace(token, actor_id=idle.actor_id),))

    def replace_armor(w):
        w.actions.set_inventory_activity(table_id, extra, True, replace_existing=True)

    unknown_coin = CoinAmount("00000000-0000-4000-8000-000000000000", 1)

    operations = (
        (True, lambda w: w.cards.update_actor(one, {"hp_current": 3})),
        (True, lambda w: w.tables.set_cell(table_id, first, quantity, 7, parsed=True)),
        (False, lambda w: w.tables.set_cell(table_id, extra, active, True, parsed=True)),
        (True, replace_armor),
        (True, lambda w: w.cards.update_card_fields(one.card_id, {"dexterity": 18})),
        (True, lambda w: w.cards.update_card_fields(armor.id, {"armor_ac": 13})),
        (True, lambda w: w.cards.update_card_fields(spare.id, {"weight": 12})),
        (False, lambda w: w.cards.update_card_fields(spare.id, {"cost": unknown_coin})),
        (False, lambda w: w.actions.set_wallet(table_id, (unknown_coin,), expected=())),
        (False, lambda w: w.cards.update_actor(one, {"hp_current": 999})),
        (True, lambda w: w.cards.update_card_fields(one.card_id, {"hp_max_mode": "auto"})),
        (True, lambda w: w.cards.apply_rules(w.cards.preview_rules((("hp_max", "2"),)))),
        (False, duplicate_token),
        (False, foreign_actor),
        (True, lambda w: w.maps.move_token(board.id, token.id, 100, 105)),
        (True, lambda w: w.maps.undo_stack(board.id).undo()),
        (True, lambda w: w.maps.undo_stack(board.id).redo()),
        (False, reject_inventory_removal),
        (True, lambda w: w.actions.delete_entity(armor.id)),
        (True, lambda w: w.actions.delete_actor(two, confirmed=True)),
    )
    for accepted, operation in operations:
        for world in worlds:
            before, revision, receipt = world.records(), world.core.serial, world.core.last_commit
            history = world.maps.undo_stack(board.id).index()
            if accepted:
                operation(world)
                assert world.core.serial == revision + 1
            else:
                with pytest.raises(ValueError):
                    operation(world)
                assert world.records() == before
                assert world.core.serial == revision and world.core.last_commit is receipt
                assert world.maps.undo_stack(board.id).index() == history
            validate_project(world.core.entities)
        assert worlds[0].records() == worlds[1].records()
        for card in worlds[0].cards.all():
            for reference in (card.id, *(ActorRef(card.id, actor.id) for actor in card.actors)):
                assert worlds[0].cards.effective(reference) == worlds[1].cards.effective(reference)

    assert worlds[0].cards.get_actor(one).value("hp_current") == 2
    assert worlds[0].maps.get_map(other_board.id).tokens == ()
    for i, world in enumerate(worlds):
        settings, records = world.records()
        root = tmp_path / f"copy-{i}"
        with closing(SQLiteProjectStore.create(root)) as store:
            asset = snapshot.assets[0]
            copyfile(tmp_path / "world" / asset.path, root / asset.path)
            result = replace(
                snapshot, cards=world.cards.all(), maps=tuple(world.maps.maps.values()),
                tables=tuple(world.tables.tables.values()), entities=tuple(e for e, _ in records),
                rules=settings.rules, assets=(asset,),
            )
            store.save(result)
        with closing(SQLiteProjectStore.open(root)) as store:
            assert runtime(store.load()).records() == world.records()


def test_edit_scope_and_rollback_of_dependency_and_history(scenario, monkeypatch):
    snapshot, one, two, idle, armor, spare, board, token, _, _ = scenario
    world = runtime(snapshot)
    entities = world.core.entities
    validation = entities.change_validator
    table_id = world.cards.get_actor(two).inventory_id
    table = world.tables.get_table(table_id)
    item_col = next(column.id for column in table.columns if column.key == "item")
    quantity = next(column.id for column in table.columns if column.key == "quantity")
    checked = []
    original = validation.affected_contexts

    def observe(collection, changes, *, complete=False):
        result = original(collection, changes, complete=complete)
        checked.append(result)
        return result

    def scan():
        pytest.fail("Local edit enumerated the project")

    with monkeypatch.context() as patch:
        patch.setattr(entities, "summaries", scan)
        patch.setattr(validation, "affected_contexts", observe)
        world.cards.update_actor(one, {"hp_current": 1})
        assert checked and all(scope == {one.card_id: {one.actor_id}} for scope in checked)
        checked.clear()
        world.tables.set_cell(table_id, table.rows[0].id, quantity, 3, parsed=True)
        assert checked and all(scope == {two.card_id: {two.actor_id}} for scope in checked)
        checked.clear()
        stack = world.maps.undo_stack(board.id)
        world.maps.move_token(board.id, token.id, 95, 100)
        assert checked and all(not scope for scope in checked)
        assert stack.index() == 1

        with pytest.raises(ValueError):
            with world.core.transaction():
                world.maps.move_token(board.id, token.id, 100, 115)
                world.tables.set_cell(table_id, table.rows[0].id, item_col, spare.id)
                world.cards.update_actor(two, {"hp_current": 999})
        assert stack.index() == 1 and world.maps.get_map(board.id).tokens[0].x == 95

        checked.clear()
        world.cards.update_card_fields(armor.id, {"armor_ac": 15})
        assert checked and all(
            scope == {
                armor.id: {None}, one.card_id: {None, one.actor_id}, two.card_id: {two.actor_id},
            }
            for scope in checked
        )
        world.tables.set_cell(table_id, table.rows[0].id, item_col, spare.id)
        checked.clear()
        world.cards.update_card_fields(armor.id, {"armor_ac": 16})
        assert checked and all(
            two.card_id not in scope and idle.card_id not in scope for scope in checked
        )

    world.core.replace(snapshot.entity_collection())
    assert world.core.entities.change_validator is not validation
    assert world.core.last_commit is None


def test_open_relations_and_inventory_keep_local_edit_scope(scenario, project, monkeypatch):
    _, one, _, _, _, _, board, token, _, _ = scenario
    app, _ = project
    editor = app.open_card_editor(one.card_id).widget()
    relation = editor.relations.rows[one.actor_id]
    assert relation.child(0).text(0) == "First"
    inventory = app.cards_service.get_actor(one).inventory_id
    assert app.actions.inventory_owner(inventory) == one

    def scan():
        pytest.fail("Local edit or inventory lookup enumerated the project")

    with monkeypatch.context() as patch:
        patch.setattr(app.core.entities, "summaries", scan)
        app.cards_service.update_actor(one, {"hp_current": 5})
        assert "5 /" in relation.text(1)
        app.maps_service.move_token(board.id, token.id, 100, 100)
        assert relation.childCount() == 1
        assert app.actions.inventory_owner(inventory) == one

    app.actions.update_entity(board.id, title="Renamed")
    assert relation.child(0).text(0) == "Renamed"
    app.maps_service.delete_token(board.id, token.id)
    assert relation.childCount() == 0


def test_receipt_includes_hp_clamped_by_item_reconcile(scenario):
    snapshot, one, _, _, armor, _, _, _, _, _ = scenario
    world = runtime(snapshot)
    world.cards.update_card_fields(one.card_id, {"hp_max_mode": "auto"})
    world.cards.update_actor(one, {"hp_current": 12})
    before = world.core.serial
    world.cards.update_card_fields(armor.id, {"modifiers": ()})
    after = world.core.last_commit
    assert after.serial == before + 1
    changes = {change.id: change for change in after.changes.aggregates}
    assert set(changes) == {armor.id, one.card_id}
    changed_card = changes[one.card_id]
    assert changed_card.before_payload.actors[0].value("hp_current") == 12
    assert changed_card.after_payload.actors[0].value("hp_current") == 8


def test_reentrant_map_edit_after_undo_replaces_redo_branch(scenario):
    snapshot, _, _, _, _, _, board, token, _, _ = scenario
    world = runtime(snapshot)
    stack = world.maps.undo_stack(board.id)
    world.maps.move_token(board.id, token.id, 100, 100)
    observed = []

    def edit_after_undo(key):
        world.maps.map_changed.disconnect(edit_after_undo)
        observed.append(stack.index())
        world.maps.move_token(key, token.id, 120, 130)

    world.maps.map_changed.connect(edit_after_undo)
    assert stack.undo()
    assert observed == [0]
    assert world.maps.get_map(board.id).tokens[0].x == 120
    assert stack.index() == 1 and not stack.canRedo()
    assert stack.undo()
    assert world.maps.get_map(board.id).tokens == (token,)
