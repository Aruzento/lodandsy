import hashlib
import sqlite3

import pytest
from PySide6.QtGui import QImage

from lodandsy.application.card_payload_codec import (
    decode_actor,
    decode_card,
    encode_card,
    encode_card_aggregate,
)
from lodandsy.application.sqlite_project_store import ProjectError, SQLiteProjectStore
from lodandsy.domain.currency import CoinAmount
from lodandsy.domain.modifiers import Modifier

pytest_plugins = ["tests.project_fixture"]


def world(project, tmp_path):
    app, controller = project
    controller.create_project(tmp_path / "Мир")
    image = QImage(64, 64, QImage.Format.Format_RGB32)
    image.fill(0)
    source = tmp_path / "map.png"
    assert image.save(str(source))
    asset = controller.store.import_asset(source)
    controller.assets[asset.id] = asset
    card = app.create_card("Player", card_type="character")
    app.cards_service.update_card_fields(card.id, {"hp_max": 100})
    app.cards_service.set_player(card.id, True, create=True)
    actor = app.cards_service.list_actors(card.id)[0]
    doc = app.maps_service.create_map("Map", asset.id)
    app.maps_service.add_token(doc.id, card.id, 10, 20, actor_id=actor.id)
    return app, controller, card, actor, doc


def test_aggregate_codec_and_normalized_backup_roundtrip(project, tmp_path):
    app, controller, card, actor, doc = world(project, tmp_path)
    item = app.create_card("Item", card_type="item")
    app.cards_service.update_card_fields(
        item.id,
        {
            "modifiers": (Modifier("ac", operand=2),),
            "cost": CoinAmount(app.economy.currency.base_id, 0),
        },
    )
    preview = app.cards_service.preview_rules((("initiative", "dexterity_mod + 2"),))
    app.cards_service.apply_rules(preview)
    saved_card = app.cards_service.get_card(card.id)
    with pytest.raises(ValueError):
        encode_card(saved_card)
    version, definition, rows, default = encode_card_aggregate(saved_card)
    actors = tuple(
        decode_actor(key, inventory, v, state) for key, owner, inventory, v, state in rows
    )
    assert (
        decode_card(
            saved_card.title,
            card.id,
            None,
            version,
            definition,
            actors=actors,
            default_actor_id=default,
        )
        == saved_card
    )
    assert controller.save_current()
    snapshot = controller.store.load()
    assert snapshot.cards == app.cards.all()
    assert snapshot.rules == app.cards_service.rules
    with sqlite3.connect(controller.store.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM card_actor").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM map_token").fetchone() == (1,)
        assert "tokens" not in {
            row[1] for row in connection.execute("PRAGMA table_info(map_document)")
        }
        assert (
            '"hp_current"'
            not in connection.execute(
                "SELECT content FROM card_content WHERE id=?", (card.id,)
            ).fetchone()[0]
        )
    backup = tmp_path / "copy.lodbackup"
    controller.store.backup(backup)
    restored = SQLiteProjectStore.restore(backup, tmp_path / "Восстановлено")
    assert restored.load() == snapshot
    restored.close()


def test_actor_token_fault_rolls_back_and_retry(project, tmp_path):
    app, controller, card, actor, doc = world(project, tmp_path)
    assert controller.save_current()
    snapshot = controller.store.load()
    with sqlite3.connect(controller.store.path) as connection:
        connection.execute(
            "CREATE TRIGGER fail_token BEFORE INSERT ON map_token "
            "BEGIN SELECT RAISE(ABORT,'injected after actors'); END"
        )
    app.cards_service.update_card_fields(card.id, {"summary": "Pending"})
    token = snapshot.maps[0].tokens[0]
    app.maps_service.move_token(doc.id, token.id, 25, 35)
    assert not controller.save_current()
    assert controller.saver.dirty and controller.saver.last_error
    assert controller.store.load() == snapshot
    with sqlite3.connect(controller.store.path) as connection:
        connection.execute("DROP TRIGGER fail_token")
    assert controller.save_current()
    assert not controller.saver.dirty
    saved = controller.store.load()
    assert (saved.maps[0].tokens[0].x, saved.maps[0].tokens[0].y) == (25, 35)
    assert next(c for c in saved.cards if c.id == card.id).value("summary") == "Pending"


def test_schema14_and_corrupt_actor_are_not_rewritten(project, tmp_path):
    app, controller, card, actor, doc = world(project, tmp_path)
    assert controller.save_current()
    path = controller.store.path
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=14")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ProjectError):
        controller.store.load()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=16")
        connection.execute("UPDATE map_token SET actor_id=?", (card.id,))
    before = path.read_bytes()
    with pytest.raises(ProjectError):
        controller.store.load()
    assert path.read_bytes() == before
    # Restore fixture-owned database so its safe-close is not a user interaction.
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE map_token SET actor_id=?", (actor.id,))
