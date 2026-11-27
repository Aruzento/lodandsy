import errno
import hashlib
import json
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from lodandsy.application import sqlite_project_store
from lodandsy.application.sqlite_project_store import (
    SCHEMA_VERSION,
    ProjectError,
    SQLiteProjectStore,
    connect_database,
)
from lodandsy.domain.map_document import MapNote
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


@pytest.mark.parametrize("version", [9, 10])
@pytest.mark.parametrize("fail", [False, True])
def test_map11_upgrade_checks_backup_and_preserves_older_world(
    project, tmp_path, qtbot, monkeypatch, version, fail,
):
    app, projects = project
    document, _ = open_map(app, projects, tmp_path, qtbot)
    card = app.create_card("Заслон", card_type="object")
    note = app.create_card("Маршрут", card_type="note")
    token = app.actions.place_card(
        document.id, card.id, 171, 128, rotation=23.125 if version == 10 else 0,
    )
    other = app.maps_service.create_map("Вторая карта", document.asset_id)
    assert projects.save_current()
    store = projects.store
    original = store.load()
    flags = replace(token, hidden=True, dead=True)
    marker = MapNote(note.id, "note", 90.25, 91.5, "Опасность")
    upgraded = replace(original, revision=original.revision + 1, maps=tuple(
        replace(m, tokens=(flags,), notes=(marker,)) if m.id == document.id else m
        for m in original.maps
    ))
    before = hashlib.sha256(store.path.read_bytes()).hexdigest()
    if fail:
        def refuse_restore(*args, **kwargs):
            raise OSError("injected restore failure")

        monkeypatch.setattr(store, "restore_with_snapshot", refuse_restore)
        with pytest.raises(OSError, match="injected restore failure"):
            store.save(upgraded)
        assert hashlib.sha256(store.path.read_bytes()).hexdigest() == before
        assert store.load() == original
        return
    assert store.load() == original
    assert hashlib.sha256(store.path.read_bytes()).hexdigest() == before
    store.save(upgraded)
    with closing(connect_database(store.path, readonly=True)) as connection:
        versions = dict(connection.execute("SELECT id,payload_version FROM map_document"))
        assert versions == {document.id: 11, other.id: 9}
        payload, = connection.execute(
            "SELECT placement FROM map_token WHERE id=?", (token.id,),
        ).fetchone()
        assert json.loads(payload)["hidden"] is True
        assert json.loads(payload)["dead"] is True
    archived, = tmp_path.glob("LODANDSY-before-Map11-*.lodbackup")
    with closing(SQLiteProjectStore.restore(archived, tmp_path / "pre-R2")) as restored:
        assert restored.project_id == store.project_id and restored.load() == original
    world = store.root
    store.close()
    with closing(SQLiteProjectStore.open(world)) as reopened:
        assert reopened.load() == upgraded
        reopened.save(replace(upgraded, revision=upgraded.revision + 1))
    assert tuple(tmp_path.glob("LODANDSY-before-Map11-*.lodbackup")) == (archived,)


@pytest.mark.parametrize("stage", ["backup", "verification"])
def test_failed_map10_upgrade_preserves_original_world(
    project, tmp_path, qtbot, monkeypatch, stage,
):
    store, _, original, updated, _ = map9_world(project, tmp_path, qtbot)
    before = hashlib.sha256(store.path.read_bytes()).hexdigest()
    if stage == "backup":
        def fail_backup(_, *, verification_root):
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


@pytest.mark.parametrize(
    "failure", ["temp-db", "archive", "temp-space", "verify-space", "budget"],
)
def test_map10_storage_budget_and_disk_failures_keep_original(
    project, tmp_path, qtbot, monkeypatch, failure,
):
    store, _, original, updated, _ = map9_world(project, tmp_path, qtbot)
    before = store.path.read_bytes()
    if failure == "temp-db":
        connect = sqlite3.connect

        def connect_with_full_temp(database, *args, **kwargs):
            if "lodandsy-backup-" in str(database):
                raise sqlite3.OperationalError("database or disk is full")
            return connect(database, *args, **kwargs)

        monkeypatch.setattr(sqlite3, "connect", connect_with_full_temp)
    elif failure == "archive":
        open_archive = zipfile.ZipFile

        def open_with_full_destination(file, mode="r", *args, **kwargs):
            if mode == "x":
                raise OSError(errno.ENOSPC, "archive destination full")
            return open_archive(file, mode, *args, **kwargs)

        monkeypatch.setattr(zipfile, "ZipFile", open_with_full_destination)
    elif failure == "temp-space":
        monkeypatch.setattr(
            sqlite_project_store.shutil, "disk_usage", lambda unused: SimpleNamespace(free=0),
        )
    elif failure == "verify-space":
        def usage(path):
            return SimpleNamespace(
                free=0 if Path(path).name.startswith("lodandsy-verify-map10-") else 2**63,
            )

        monkeypatch.setattr(sqlite_project_store.shutil, "disk_usage", usage)
    else:
        monkeypatch.setattr(sqlite_project_store, "MAX_BACKUP_BYTES", len(before) - 1)
    expected = OSError if failure == "archive" else ProjectError
    with pytest.raises(expected) as error:
        store.save(updated)
    assert store.path.read_bytes() == before and store.load() == original
    backups = tuple(tmp_path.glob("LODANDSY-before-Map10-*.lodbackup"))
    assert len(backups) == (1 if failure == "verify-space" else 0)
    assert not tuple(tmp_path.glob("LODANDSY-before-Map10-*.tmp"))
    if failure in {"temp-db", "temp-space"}:
        assert sqlite_project_store.TEMP_DB_STAGE in str(error.value)
        assert str(Path(tempfile.gettempdir()).resolve()) in str(error.value)
    if failure == "temp-db":
        assert isinstance(error.value.__cause__, sqlite3.OperationalError)
    if failure == "archive":
        assert sqlite_project_store.ARCHIVE_STAGE in str(error.value)
        assert str(tmp_path) in str(error.value)
        assert error.value.__cause__.errno == errno.ENOSPC
    if failure == "verify-space":
        assert sqlite_project_store.VERIFY_STAGE in str(error.value)
    if failure != "budget":
        assert "Недостаточно свободного места" in str(error.value)
        assert "Требуется " in str(error.value) and " байт" in str(error.value)
    if failure == "budget":
        assert "4 GiB" in str(error.value)


@pytest.mark.parametrize("batch", [False, True])
def test_map10_multiple_map_upgrades_only_backup_the_required_writes(
    project, tmp_path, qtbot, batch,
):
    store, key, _, updated, transformed = map9_world(project, tmp_path, qtbot)
    app, projects = project
    other_key = next(m.id for m in updated.maps if m.id != key)
    other_token = app.actions.place_card(other_key, transformed.card_id, 100, 100)
    assert projects.save_current()
    initial = store.load()
    first_map = next(m for m in updated.maps if m.id == key)
    other_map = next(m for m in initial.maps if m.id == other_key)
    second_map = replace(other_map, tokens=(replace(other_token, rotation=16.75),))
    if not batch:
        store.save(replace(initial, revision=initial.revision + 1, maps=(first_map, other_map)))
    revision = initial.revision + (1 if batch else 2)
    final = replace(initial, revision=revision, maps=(first_map, second_map))
    store.save(final)
    loaded = store.load()
    assert {m.id: m for m in loaded.maps} == {m.id: m for m in final.maps}
    backups = tuple(tmp_path.glob("LODANDSY-before-Map10-*.lodbackup"))
    assert len(backups) == (1 if batch else 2)
    store.save(replace(loaded, revision=revision + 1))
    assert set(tmp_path.glob("LODANDSY-before-Map10-*.lodbackup")) == set(backups)
