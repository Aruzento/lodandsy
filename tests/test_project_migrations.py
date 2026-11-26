import hashlib
import json
from contextlib import closing
from dataclasses import replace

import pytest

from lodandsy.application.sqlite_project_store import (
    SCHEMA_VERSION,
    ProjectError,
    SQLiteProjectStore,
    connect_database,
)
from tests.test_map_tokens_grid import open_map

pytest_plugins = ["tests.project_fixture"]


@pytest.mark.parametrize("version", [*range(1, SCHEMA_VERSION), SCHEMA_VERSION + 1, 999])
def test_unsupported_schemas_refuse_without_modifying_files(tmp_path, version):
    store = SQLiteProjectStore.create(tmp_path / "world")
    with closing(connect_database(store.path)) as c, c:
        c.execute(f"PRAGMA user_version={version}")
    store.close()
    before = hashlib.sha256(store.path.read_bytes()).hexdigest()
    with pytest.raises(ProjectError, match="Unsupported project schema"):
        SQLiteProjectStore.open(store.root)
    assert hashlib.sha256(store.path.read_bytes()).hexdigest() == before


def map9_world(project, tmp_path, qtbot):
    app, projects = project
    document, _ = open_map(app, projects, tmp_path, qtbot)
    card = app.create_card("Сундук", card_type="object")
    token = app.actions.place_card(document.id, card.id, 100, 110, cells_w=2, cells_h=1)
    second = app.actions.place_card(document.id, card.id, 240, 240)
    app.maps_service.create_map("Другая карта", document.asset_id)
    extra = projects.store.root / "assets" / "original-notes.txt"
    extra.write_bytes(b"extra asset")
    assert projects.save_current()
    store = projects.store
    original = store.load()
    transformed = replace(token, cells_w=0.0134567891234567, cells_h=1.1375, rotation=37.35)
    updated = replace(original, revision=original.revision + 1, maps=tuple(
        replace(m, tokens=(transformed, second)) if m.id == document.id else m
        for m in original.maps
    ))
    return store, document.id, original, updated, transformed


def test_map10_upgrade_backs_up_existing_world_and_reopens_without_rewriting(
    project, tmp_path, qtbot,
):
    store, key, original, updated, transformed = map9_world(project, tmp_path, qtbot)
    before = store.path.read_bytes()
    project_id = store.project_id
    assert store.load() == original
    assert store.path.read_bytes() == before
    assert not tuple(tmp_path.glob("LODANDSY-before-Map10-*.lodbackup"))

    store.save(updated)
    assert store.load() == updated
    with closing(connect_database(store.path, readonly=True)) as connection:
        versions = dict(connection.execute("SELECT id,payload_version FROM map_document"))
        assert versions.pop(key) == 10 and list(versions.values()) == [9]
        payload, = connection.execute(
            "SELECT placement FROM map_token WHERE id=?", (transformed.id,),
        ).fetchone()
        values = json.loads(payload)
        assert values["cells_w"] == transformed.cells_w and values["rotation"] == 37.35
    backup, = tmp_path.glob("LODANDSY-before-Map10-*.lodbackup")
    with closing(SQLiteProjectStore.restore(backup, tmp_path / "verified")) as restored:
        assert restored.load() == original and restored.project_id == project_id
        assert (restored.root / "assets" / "original-notes.txt").read_bytes() == b"extra asset"

    path = store.root
    migrated = store.path.read_bytes()
    store.close()
    with closing(SQLiteProjectStore.open(path)) as reopened:
        assert reopened.load() == updated and reopened.path.read_bytes() == migrated
        # A subsequent write using only legacy geometry keeps Map10 without a
        # second conversion or another backup.
        reopened.save(replace(original, revision=updated.revision + 1))
        with closing(connect_database(reopened.path, readonly=True)) as connection:
            assert connection.execute(
                "SELECT payload_version FROM map_document WHERE id=?", (key,),
            ).fetchone() == (10,)
    assert tuple(tmp_path.glob("LODANDSY-before-Map10-*.lodbackup")) == (backup,)


@pytest.mark.parametrize("stage", ["backup", "verification"])
def test_failed_map10_upgrade_preserves_original_world(
    project, tmp_path, qtbot, monkeypatch, stage,
):
    store, _, original, updated, _ = map9_world(project, tmp_path, qtbot)
    before = hashlib.sha256(store.path.read_bytes()).hexdigest()
    if stage == "backup":
        def fail_backup(_):
            raise OSError("fault before migration")

        monkeypatch.setattr(store, "backup", fail_backup)
        with pytest.raises(OSError, match="fault before migration"):
            store.save(updated)
    else:
        load = SQLiteProjectStore._load_modules

        def fail_verification(connection):
            if connection.execute(
                "SELECT 1 FROM map_document WHERE payload_version=10",
            ).fetchone():
                raise ProjectError("fault during verification")
            return load(connection)

        monkeypatch.setattr(SQLiteProjectStore, "_load_modules", staticmethod(fail_verification))
        with pytest.raises(ProjectError, match="fault during verification"):
            store.save(updated)
        assert len(list(tmp_path.glob("LODANDSY-before-Map10-*.lodbackup"))) == 1
    assert hashlib.sha256(store.path.read_bytes()).hexdigest() == before
    assert store.load() == original
