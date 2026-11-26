import pytest

from lodandsy.application.entity_session import EntitySession
from lodandsy.domain.entity import EntityCollection

pytest_plugins = ["tests.project_fixture"]


def test_inventory_owner_reads_committed_snapshot_at_publication(project):
    app, _ = project
    card = app.create_card("Страж", card_type="character")
    observed = []
    signature = app.core.serial
    assert app.actions.inventory_owner(card.id) is None  # prime the stable cache
    app.cards_service.actor_changed.connect(
        lambda card_id, actor_id, fields: observed.append(
            (app.core.serial, app.actions.inventory_owner(inventory_id))
        )
    )
    with app.core.transaction():
        ref = app.cards_service.create_actor(card.id)
        inventory_id = app.cards_service.get_actor(ref).inventory_id
        assert observed == []
    assert observed and all(state == (signature + 1, ref) for state in observed)


def test_rolled_back_inventory_lookup_cannot_pollute_committed_cache(project):
    app, _ = project
    card = app.create_card("Страж", card_type="character")
    signature = app.core.serial
    with pytest.raises(ValueError, match="rollback"):
        with app.core.transaction():
            ref = app.cards_service.create_actor(card.id)
            inventory_id = app.cards_service.get_actor(ref).inventory_id
            assert app.actions.inventory_owner(inventory_id) == ref
            raise ValueError("rollback")
    assert app.core.serial == signature
    assert app.actions.inventory_owner(inventory_id) is None


def test_save_observes_each_commit_even_if_callback_reenters_then_raises(
    project, tmp_path, caplog
):
    app, projects = project
    assert projects.create_project(tmp_path / "world")
    card = app.create_card("Исходное название")
    assert projects.save_current()
    start = app.core.serial, projects.saver.revision
    observed = []
    app.core.committed.connect(
        lambda: observed.append(("dirty", app.core.serial, projects.saver.revision))
    )

    def spawn_commit():
        assert projects.saver.dirty
        with app.core.transaction():
            app.actions.update_entity(card.id, title="Вложенный коммит")
            app.core.after_commit(lambda: observed.append(("inner",)))
        assert projects.saver.revision == start[1] + 2
        raise RuntimeError("notification failed")

    with app.core.transaction():
        app.actions.update_entity(card.id, title="Внешний коммит")
        app.core.after_commit(spawn_commit)
        app.core.after_commit(lambda: observed.append(("outer",)))
    assert observed == [
        ("dirty", start[0] + 1, start[1] + 1),
        ("dirty", start[0] + 2, start[1] + 2),
        ("outer",),
        ("inner",),
    ]
    assert "notification failed" in caplog.text
    assert projects.save_current()
    snapshot = projects.store.load()
    assert snapshot.revision == start[1] + 2
    assert snapshot.cards[0].title == "Вложенный коммит"


def test_project_replacement_retires_pending_notifications(qapp):
    core = EntitySession()
    observed = []
    with core.transaction():
        core.after_commit(lambda: core.replace(EntityCollection()))
        core.after_commit(lambda: observed.append("old project"))
        core.mark_changed()
    assert observed == []
    assert core.serial == core.generation == 1


def test_project_selection_notification_cannot_cache_previous_inventory(project):
    app, _ = project
    card = app.create_card("Страж", card_type="character")
    actor = app.cards_service.get_actor(app.cards_service.create_actor(card.id))
    app.core.select(card.id)
    observed = []
    app.core.selection_changed.connect(
        lambda selection: observed.append(app.actions.inventory_owner(actor.inventory_id))
    )
    app.core.replace(EntityCollection())
    assert observed == [None]
    assert app.actions.inventory_owner(actor.inventory_id) is None
