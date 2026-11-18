import sqlite3
from contextlib import closing

import pytest

from lodandsy.application.sqlite_project_store import (
    ProjectError,
    ProjectSnapshot,
    SQLiteProjectStore,
    connect_database,
)
from lodandsy.domain.card_collection import CardCollection


def make_v1(tmp_path):
    store = SQLiteProjectStore.create(tmp_path / "world")
    cards = CardCollection()
    cards.create("Original")
    store.save(ProjectSnapshot(cards.all(), 1))
    with closing(connect_database(store.path)) as connection, connection:
        connection.execute("DROP TABLE map_document")
        connection.execute("DROP TABLE random_table")
        connection.execute("DROP INDEX entity_parent_position")
        connection.execute("PRAGMA user_version=1")
    store.close()
    return store.root, cards.all()


def test_v1_migration_is_backed_up_and_reopening_is_idempotent(tmp_path):
    root, cards = make_v1(tmp_path)
    store = SQLiteProjectStore.open(root)
    assert store.load().cards == cards
    backups = list((root / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with closing(connect_database(backups[0], readonly=True)) as backup:
        assert backup.execute("PRAGMA user_version").fetchone() == (1,)
        assert backup.execute("SELECT title FROM entity").fetchall() == [("Original",)]
    store.close()
    reopened = SQLiteProjectStore.open(root)
    assert reopened.load().cards == cards
    assert len(list((root / "backups").glob("*.sqlite3"))) == 1
    reopened.close()


def test_failed_migration_rolls_back_schema_and_keeps_data_and_backup(tmp_path, monkeypatch):
    root, cards = make_v1(tmp_path)
    def fail(connection):
        connection.execute("CREATE INDEX half_migration ON entity(title)")
        raise sqlite3.OperationalError("interrupted migration")
    monkeypatch.setattr(SQLiteProjectStore, "_upgrade_v1", staticmethod(fail))
    with pytest.raises(ProjectError, match="original schema retained"):
        SQLiteProjectStore.open(root)
    with closing(connect_database(root / "project.sqlite3", readonly=True)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute("SELECT title FROM entity").fetchall() == [("Original",)]
        assert not connection.execute(
            "SELECT name FROM sqlite_master WHERE name='half_migration'"
        ).fetchall()
    assert len(list((root / "backups").glob("*.sqlite3"))) == 1
