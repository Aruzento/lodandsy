import os
import sqlite3
import subprocess
import sys
from contextlib import ExitStack, closing
from dataclasses import replace
from shutil import copyfile
from threading import Event
from uuid import uuid4

import pytest
from PySide6.QtCore import QRectF, QTimer
from PySide6.QtGui import QPainterPath

from lodandsy.application import sqlite_project_store
from lodandsy.application.sqlite_project_store import (
    ProjectError,
    ProjectSnapshot,
    SQLiteProjectStore,
    connect_database,
)
from lodandsy.domain.actor_state import ActorRef
from lodandsy.domain.card import Card
from lodandsy.domain.currency import CoinAmount
from lodandsy.domain.item_categories import ItemCategory
from lodandsy.domain.map_document import MapShape

pytest_plugins = ["tests.project_fixture"]


def test_incremental_and_full_writes_roundtrip_the_same_project_operations(project, tmp_path):
    from tests.test_equipment import character, item, row
    from tests.test_map_tokens_grid import image_file

    app, projects = project
    assert projects.create_project(tmp_path / "source")
    source = projects.store
    board = source.import_asset(image_file(tmp_path / "board.png"))
    extra = source.import_asset(image_file(tmp_path / "extra.png", width=45))
    projects.assets[board.id] = board
    card, template = character(app)
    armor = item(app)
    row(app, template.id, armor, active=True)
    row(app, template.id, armor, count=3)
    app.cards_service.update_card_fields(card.id, {"hp_max": 22})
    map_doc = app.maps_service.create_map("Карта", board.id)
    card_folder = app.create_card("Папка", card_type="folder")

    checkpoints = []

    def capture():
        checkpoints.append(projects._snapshot(len(checkpoints) + 1))

    capture()
    with app.core.transaction():
        app.actions.update_entity(card.id, parent_id=card_folder.id, title="Страж")
        token = app.actions.place_card(map_doc.id, card.id, 90, 90)
        ref = ActorRef(card.id, token.actor_id)
        app.cards_service.update_actor(ref, {"hp_current": 11})
    capture()

    inventory = app.tables_service.get_table(app.cards_service.get_actor(ref).inventory_id)
    coins = (CoinAmount(app.economy.currency.base_id, 7),)
    app.actions.set_wallet(inventory.id, coins, expected=())
    inventory = app.tables_service.get_table(inventory.id)
    app.tables_service.edit_table(
        inventory.id,
        columns=tuple(replace(col, position=i) for i, col in enumerate(
            reversed(inventory.columns)
        )),
        rows=tuple(replace(entry, position=i) for i, entry in enumerate(
            reversed(inventory.rows)
        )),
    )
    app.cards_service.update_card_fields(armor.id, {"armor_ac": 16})
    expected_stats = app.cards_service.effective(ref)
    fog = QPainterPath()
    fog.addRect(QRectF(1, 2, 20, 25))
    app.maps_service.edit_fog(map_doc.id, fog)
    app.maps_service.put_vector(map_doc.id, MapShape("circle", ((30, 0),), x=120, y=145))
    app.maps_service.move_token(map_doc.id, token.id, 112, 128)
    capture()
    history = app.maps_service.undo_stack(map_doc.id)
    assert history.undo()
    capture()
    assert history.redo()

    economy = app.economy.settings
    app.economy.apply_settings(economy, economy.currency, (ItemCategory(str(uuid4()), "Провизия"),))
    app.cards_service.apply_rules(app.cards_service.preview_rules((("initiative", "2"),)))
    projects.assets[extra.id] = extra
    capture()
    app.actions.delete_actor(ref, confirmed=True)
    projects.assets.pop(extra.id)
    capture()

    with ExitStack() as stack:
        stores = [
            stack.enter_context(closing(SQLiteProjectStore.create(tmp_path / name)))
            for name in ("incremental", "full")
        ]
        for store in stores:
            for asset in (board, extra):
                copyfile(source.root / asset.path, store.root / asset.path)
        for snapshot in checkpoints:
            stores[0].save(snapshot, snapshot.revision - 1)
            stores[1].save(snapshot, snapshot.revision - 1, _rewrite_all=True)
            incremental, full = (store.load() for store in stores)
            assert incremental == full
            if snapshot.revision == 3:
                from lodandsy.application.cards_service import CardsService
                from lodandsy.domain.card_collection import CardCollection

                cards = CardsService(CardCollection(entities=incremental.entity_collection()))
                from lodandsy.domain.document_payloads import inventory_inputs

                cards.calculation_inputs = lambda c, a: inventory_inputs(cards.entities, c, a)
                assert cards.get_actor(ref).value("hp_current") == 11
                assert cards.effective(ref) == expected_stats
                assert next(t for t in incremental.tables if t.id == inventory.id).wallet == coins

        copies = []
        for i, store in enumerate(stores):
            archive = tmp_path / f"world-{i}.lodbackup"
            store.backup(archive)
            store.close()
            with closing(SQLiteProjectStore.open(store.root)) as reopened:
                assert reopened.load() == incremental
            with closing(SQLiteProjectStore.restore(archive, tmp_path / f"restore-{i}")) as copy:
                copies.append(copy.load())
                assert copy.load().assets == (board,)
                assert (copy.root / extra.path).is_file()
        assert copies == [incremental, incremental]
        assert ref.actor_id not in {a.id for c in incremental.cards for a in c.actors}


def test_local_write_preserves_other_rows_and_decodes_modules_once(tmp_path, monkeypatch):
    a, b = Card("Changed"), Card("Independent")
    with closing(SQLiteProjectStore.create(tmp_path / "world")) as store:
        store.save(ProjectSnapshot((a, b), 1))
        with closing(connect_database(store.path)) as connection, connection:
            connection.execute(
                f"CREATE TRIGGER preserve_card BEFORE DELETE ON card_content WHEN OLD.id='{b.id}' "
                "BEGIN SELECT RAISE(ABORT,'unrelated aggregate rewritten'); END"
            )
        calls = []
        decode = SQLiteProjectStore._load_modules

        def observe(connection):
            calls.append(connection.in_transaction)
            return decode(connection)

        monkeypatch.setattr(SQLiteProjectStore, "_load_modules", staticmethod(observe))
        store.save(ProjectSnapshot((replace(a, title="Edited"), b), 2), 1)
        assert calls == [True]
        assert store.load().cards[1] == b


def test_compound_failure_rolls_back_and_allows_same_revision_retry(tmp_path):
    from tests.project_fixture import sample_store

    with closing(sample_store(tmp_path / "world")) as store:
        base = store.load()
        document = base.maps[0]
        table = base.tables[0]
        changed = replace(
            base, revision=base.revision + 2,
            cards=(base.cards[0].with_fields({"summary": "Updated"}), *base.cards[1:]),
            maps=(replace(document, tokens=(replace(document.tokens[0], x=122),)),),
            tables=(table.with_cell(table.rows[0].id, table.columns[0].id, "Later"),),
        )
        with closing(connect_database(store.path)) as connection, connection:
            connection.execute(
                "CREATE TRIGGER fail_cell BEFORE INSERT ON table_cell "
                "BEGIN SELECT RAISE(ABORT,'fault after writing Card and Map'); END"
            )
        before = store.path.read_bytes()
        with pytest.raises(ProjectError, match="fault after writing"):
            store.save(changed, base.revision)
        assert store.path.read_bytes() == before
        assert store.load() == base
        with closing(connect_database(store.path)) as connection, connection:
            connection.execute("DROP TRIGGER fail_cell")
        store.save(changed, base.revision)
        assert store.load() == changed


@pytest.mark.parametrize("newer", [False, True])
def test_commit_error_is_reconciled_before_retry(tmp_path, monkeypatch, newer):
    card = Card("Before")
    with closing(SQLiteProjectStore.create(tmp_path / "world")) as store:
        store.save(ProjectSnapshot((card,), 1))
        pending = ProjectSnapshot((replace(card, title="Committed"),), 3)

        class LostReturn(sqlite3.Connection):
            def commit(self):
                super().commit()
                raise OSError("lost result after SQLite commit")

        connect = sqlite_project_store.connect_database

        def open_writer(path, *, readonly=False):
            if readonly:
                return connect(path, readonly=True)
            connection = sqlite3.connect(path, factory=LostReturn)
            connection.execute("PRAGMA foreign_keys=ON")
            return connection

        with monkeypatch.context() as patch:
            patch.setattr(sqlite_project_store, "connect_database", open_writer)
            with pytest.raises(OSError, match="lost result"):
                store.save(pending, 1)
        assert store.load() == pending

        if newer:
            replacement = ProjectSnapshot((replace(card, title="Newer"),), 4)
            store.save(replacement, 1)
            assert store.load() == replacement
        else:
            with monkeypatch.context() as patch:
                patch.setattr(store, "_write_delta", lambda *_: pytest.fail("retry issued DML"))
                store.save(pending, 1)
                store.save(pending, 1)  # A second lost notification still has the same base.
            assert store.load() == pending
        with pytest.raises(ProjectError, match="Acknowledged revision"):
            store.save(ProjectSnapshot((card,), 5), 0)


@pytest.mark.parametrize("mutation", ["revision", "contents", "file", "identity", "unsupported"])
def test_unexpected_base_is_refused_without_rewrite(tmp_path, mutation):
    with closing(SQLiteProjectStore.create(tmp_path / "world")) as store:
        card = Card("Original")
        store.save(ProjectSnapshot((card,), 1))
        if mutation == "file":
            path = tmp_path / "same-project.sqlite3"
            copyfile(store.path, path)
            os.replace(path, store.path)
        else:
            with closing(connect_database(store.path)) as connection, connection:
                match mutation:
                    case "revision":
                        connection.execute("UPDATE metadata SET revision=7")
                    case "contents":
                        connection.execute("UPDATE entity SET title='Changed externally'")
                    case "identity":
                        connection.execute("UPDATE metadata SET project_id=?", (str(uuid4()),))
                    case "unsupported":
                        connection.execute("UPDATE card_content SET payload_version=999")
        before = store.path.read_bytes()
        with pytest.raises(ProjectError):
            store.save(ProjectSnapshot((replace(card, title="Would overwrite"),), 8), 1)
        assert store.path.read_bytes() == before


def test_shutdown_waits_for_the_writer_and_releases_project_lease(project, tmp_path, qtbot):
    app, controller = project
    root = tmp_path / "world"
    assert controller.create_project(root)
    original = controller.store.save
    entered, release = Event(), Event()

    def delayed(snapshot, base):
        entered.set()
        assert release.wait(4)
        original(snapshot, base)

    controller.saver._persist = delayed
    app.create_card("Pending")
    assert controller.saver.request_save()
    qtbot.waitUntil(entered.is_set)
    QTimer.singleShot(25, release.set)
    assert controller.can_close()
    with closing(SQLiteProjectStore.open(root)) as store:
        assert store.load().cards[0].title == "Pending"


def test_new_edits_after_lost_ack_are_saved_through_the_same_pipeline(project, tmp_path):
    app, controller = project
    assert controller.create_project(tmp_path / "world")
    card = app.create_card("First")
    writer = controller.saver._persist

    def lose_ack(snapshot, base):
        writer(snapshot, base)
        raise OSError("lost ACK")

    controller.saver._persist = lose_ack
    assert not controller.saver.save()
    assert controller.saver.saved_revision == 0 and controller.store.load().revision == 1
    app.actions.update_entity(card.id, title="Second")
    controller.saver._persist = writer
    assert controller.saver.save()
    assert controller.saver.saved_revision == 2
    assert controller.store.load().cards[0].title == "Second"


def test_process_exit_mid_write_reopens_the_old_revision(tmp_path):
    root = tmp_path / "world"
    base = ProjectSnapshot((Card("Before"),), 1)
    with closing(SQLiteProjectStore.create(root)) as store:
        store.save(base)
    interrupted = subprocess.run(
        [sys.executable, "-c", """
import os
import sys
from dataclasses import replace
from pathlib import Path
from lodandsy.application.sqlite_project_store import SQLiteProjectStore

store, verified = SQLiteProjectStore.open_with_snapshot(Path(sys.argv[1]))
apply = store._write_delta
def interrupt(*args):
    apply(*args)
    os._exit(73)
store._write_delta = interrupt
base = verified.snapshot
store.save(replace(base, revision=2, cards=(), entities=()), 1)
""", str(root)],
        timeout=15, check=False, capture_output=True,
    )
    assert interrupted.returncode == 73, interrupted.stderr
    with closing(SQLiteProjectStore.open(root)) as reopened:
        assert reopened.load() == base
