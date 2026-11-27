import errno
import hashlib
import shutil
import zipfile
from contextlib import closing
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest

from lodandsy.application import sqlite_project_store
from lodandsy.application.rich_html import sanitize_html, text_document
from lodandsy.application.sqlite_project_store import (
    ProjectError,
    ProjectSnapshot,
    SQLiteProjectStore,
    connect_database,
)
from lodandsy.domain.card_collection import CardCollection


@pytest.fixture
def store(tmp_path):
    project = SQLiteProjectStore.create(tmp_path / "Мир")
    yield project
    project.close()


def make_cards():
    cards = CardCollection()
    a, b = cards.create("А"), cards.create("Б")
    child = cards.create("Дочерняя", a.id)
    cards.update(child.id, content=text_document("# Исходник\n\n**Markdown**\n\tTail  "))
    return cards, a, b, child


@pytest.mark.parametrize(
    "path,checksum",
    [
        (b"assets/image.png", "0" * 64),
        ("assets/image.png", b"0" * 64),
        ("assets/image\0.png", "0" * 64),
    ],
)
def test_malformed_asset_values_are_diagnosed_without_rewriting_database(store, path, checksum):
    with closing(connect_database(store.path)) as connection, connection:
        connection.execute(
            "INSERT INTO asset VALUES(?,?,?,?)", (str(UUID(int=1)), path, checksum, 0)
        )
    with pytest.raises(ProjectError, match="Invalid asset"):
        store.load()
    with closing(connect_database(store.path)) as connection:
        assert connection.execute("SELECT path,sha256 FROM asset").fetchone() == (path, checksum)


def test_create_save_close_reopen_preserves_ids_document_hierarchy_and_order(store):
    cards, a, b, child = make_cards()
    cards.update(b.id, position=0)
    store.save(ProjectSnapshot(cards.all(), 1))
    store.close()
    reopened = SQLiteProjectStore.open(store.root)
    try:
        snapshot = reopened.load()
        assert snapshot.cards == cards.all()
        loaded = CardCollection(snapshot.cards)
        assert loaded.child_ids(None) == (b.id, a.id)
        assert loaded.get(child.id).content == text_document("# Исходник\n\n**Markdown**\n\tTail  ")
        assert snapshot.revision == 1
        assert loaded.get(child.id).parent_id == a.id
    finally:
        reopened.close()


def test_second_writer_is_rejected_and_lock_released_on_close(store):
    with pytest.raises(ProjectError, match="already open"):
        SQLiteProjectStore.open(store.root)
    store.close()
    reopened = SQLiteProjectStore.open(store.root)
    reopened.close()


def test_save_is_transactional_and_older_revision_is_rejected(store):
    cards, a, b, child = make_cards()
    store.save(ProjectSnapshot(cards.all(), 1))
    before = store.load()
    connection = connect_database(store.path)
    assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
    connection.execute(
        "CREATE TRIGGER fail_insert BEFORE INSERT ON entity WHEN NEW.title='Bad' "
        "BEGIN SELECT RAISE(ABORT,'simulated disk write failure'); END"
    )
    connection.commit()
    connection.close()
    cards.rename(child.id, "Bad")
    with pytest.raises(ProjectError, match="simulated"):
        store.save(ProjectSnapshot(cards.all(), 2))
    assert store.load() == before
    with pytest.raises(ProjectError, match="Stale"):
        store.save(before)
    assert store.load() == before


def test_cascade_delete_is_committed_as_one_snapshot(store):
    cards, a, b, child = make_cards()
    store.save(ProjectSnapshot(cards.all(), 1))
    cards.delete(a.id)
    store.save(ProjectSnapshot(cards.all(), 2))
    assert store.load().cards == (b,)


@pytest.mark.parametrize(
    "mutation",
    [
        "PRAGMA user_version=999",
        "UPDATE entity SET kind='future'",
        "UPDATE card_content SET payload_version=999",
        "UPDATE entity SET parent_id=id",
        "UPDATE entity SET position=10",
    ],
)
def test_unsupported_or_invalid_data_is_not_rewritten(store, mutation):
    cards = CardCollection()
    cards.create("Card")
    store.save(ProjectSnapshot(cards.all(), 1))
    connection = connect_database(store.path)
    connection.execute(mutation)
    connection.commit()
    connection.close()
    store.close()
    before = hashlib.sha256(store.path.read_bytes()).digest()
    with pytest.raises(ValueError):
        SQLiteProjectStore.open(store.root)
    assert hashlib.sha256(store.path.read_bytes()).digest() == before


def test_corrupt_database_is_diagnosed_without_replacement(tmp_path):
    root = tmp_path / "Broken"
    root.mkdir()
    path = root / "project.sqlite3"
    path.write_bytes(b"not a SQLite database")
    with pytest.raises(ProjectError, match="Не удалось прочитать версию"):
        SQLiteProjectStore.open(root)
    assert path.read_bytes() == b"not a SQLite database"


def test_asset_is_published_before_database_reference_and_backup_restores_it(store, tmp_path):
    source = tmp_path / "image.png"
    source.write_bytes(b"resource bytes")
    asset = store.import_asset(source)
    assert (store.root / asset.path).read_bytes() == source.read_bytes()
    assert store.load().assets == ()
    cards, a, b, child = make_cards()
    store.save(ProjectSnapshot(cards.all(), 1, (asset,)))
    archive = tmp_path / "copy.lodbackup"
    store.backup(archive)
    restored = SQLiteProjectStore.restore(archive, tmp_path / "Восстановлено")
    try:
        assert restored.load() == store.load()
        assert (restored.root / asset.path).read_bytes() == source.read_bytes()
    finally:
        restored.close()


def test_missing_new_asset_and_failed_import_do_not_publish_references(
    store, tmp_path, monkeypatch
):
    source = tmp_path / "asset.png"
    source.write_bytes(b"bytes")
    asset = store.import_asset(source)
    (store.root / asset.path).unlink()
    with pytest.raises(ProjectError, match="Missing"):
        store.save(ProjectSnapshot((), 1, (asset,)))
    assert store.load().revision == 0
    assert store.load().assets == ()

    def fail_replace(*args):
        raise OSError("simulated replacement failure")

    monkeypatch.setattr("lodandsy.application.sqlite_project_store.os.replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        store.import_asset(source)
    assert list((store.root / "assets").iterdir()) == []


def test_existing_missing_asset_remains_diagnosable_and_backup_refuses_incomplete_copy(
    store, tmp_path
):
    source = tmp_path / "asset.png"
    source.write_bytes(b"bytes")
    asset = store.import_asset(source)
    store.save(ProjectSnapshot((), 1, (asset,)))
    (store.root / asset.path).unlink()
    store.save(ProjectSnapshot((), 2, (asset,)))
    assert store.load().assets == (asset,)
    with pytest.raises(ProjectError, match="Missing"):
        store.backup(tmp_path / "bad.lodbackup")
    assert not (tmp_path / "bad.lodbackup").exists()


def test_restore_rejects_traversal_and_never_overwrites_existing_folder(tmp_path):
    archive = tmp_path / "bad.lodbackup"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("project.sqlite3", b"unused")
        bundle.writestr("assets/../../escape", b"bad")
    with pytest.raises(ProjectError, match="Unsafe"):
        SQLiteProjectStore.restore(archive, tmp_path / "new")
    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "new").exists()
    with pytest.raises(ProjectError, match="never overwritten"):
        SQLiteProjectStore.restore(archive, tmp_path)


def test_asset_paths_cannot_escape_project(store, tmp_path):
    source = tmp_path / "asset.bin"
    source.write_bytes(b"bytes")
    asset = store.import_asset(source)
    for path in ["../escape", "assets/../escape", "assets\\escape", "assets/C:escape"]:
        with pytest.raises(ProjectError):
            replace(asset, path=path)


def test_backup_preserves_unregistered_document_assets(store, tmp_path):
    folder = store.root / "assets/user-images"
    folder.mkdir()
    (folder / "image.png").write_bytes(b"user image bytes")
    cards = CardCollection()
    card = cards.create("With image")
    cards.update_content(
        card.id, sanitize_html('<p><img src="assets/user-images/image.png"></p>')[0]
    )
    store.save(ProjectSnapshot(cards.all(), 1))
    archive = tmp_path / "with-user-assets.lodbackup"
    store.backup(archive)
    restored = SQLiteProjectStore.restore(archive, tmp_path / "restored")
    try:
        assert restored.load().cards == cards.all()
        assert (restored.root / "assets/user-images/image.png").read_bytes() == b"user image bytes"
    finally:
        restored.close()


def test_asset_id_collision_never_overwrites_existing_bytes(store, tmp_path, monkeypatch):
    source = tmp_path / "image.png"
    source.write_bytes(b"original")
    asset = store.import_asset(source)
    store.save(ProjectSnapshot((), 1, (asset,)))
    source.write_bytes(b"replacement")
    monkeypatch.setattr("lodandsy.application.sqlite_project_store.uuid4", lambda: UUID(asset.id))
    with pytest.raises(ProjectError, match="collision"):
        store.import_asset(source)
    assert (store.root / asset.path).read_bytes() == b"original"
    assert store.load().assets == (asset,)


def test_database_error_during_backup_is_reported_and_does_not_replace_previous_copy(
    store, tmp_path
):
    store.path.write_bytes(b"damaged database")
    previous = tmp_path / "previous.lodbackup"
    previous.write_bytes(b"previous backup bytes")
    with pytest.raises(ProjectError, match="backup failed"):
        store.backup(previous)
    assert previous.read_bytes() == b"previous backup bytes"
    assert store.path.read_bytes() == b"damaged database"


@pytest.mark.parametrize(
    "shared,phase,temp_free,destination_free,needed",
    [
        (True, "sqlite", 199, 199, 200),
        (True, "archive", 549, 549, 550),
        (False, "archive", 10000, 349, 350),
        (True, "verify", 1349, 1349, 1350),
        (False, "verify", 999, 10000, 1000),
    ],
)
def test_backup_preflight_accounts_for_peak_on_each_volume(
    tmp_path, monkeypatch, shared, phase, temp_free, destination_free, needed,
):
    temporary, archive_dir = tmp_path / "TEMP", tmp_path / "archive"
    monkeypatch.setattr(
        sqlite_project_store, "_volume_identity",
        lambda path: 1 if shared or path == temporary else 2,
    )
    monkeypatch.setattr(
        shutil, "disk_usage",
        lambda path: SimpleNamespace(free=temp_free if path == temporary else destination_free),
    )
    expected_stage, expected_directory = {
        "sqlite": (sqlite_project_store.TEMP_DB_STAGE, temporary),
        "archive": (sqlite_project_store.ARCHIVE_STAGE, archive_dir),
        "verify": (sqlite_project_store.VERIFY_STAGE, temporary),
    }[phase]
    with pytest.raises(ProjectError, match="Недостаточно") as error:
        sqlite_project_store._preflight_backup(
            temporary, archive_dir, 200, 350, 1000, temporary,
        )
    assert expected_stage in str(error.value)
    assert str(expected_directory) in str(error.value)
    assert f"Требуется {needed} байт" in str(error.value)


def test_streamed_registered_asset_uses_zip64_and_restores(store, tmp_path, monkeypatch):
    source = tmp_path / "asset.bin"
    source.write_bytes(bytes(range(256)) * 4)
    asset = store.import_asset(source)
    store.save(ProjectSnapshot((), 1, (asset,)))
    archive = tmp_path / "zip64.lodbackup"
    # Lower the allocation threshold while testing the actual ZIP64 container.
    monkeypatch.setattr(zipfile, "ZIP64_LIMIT", 512)
    store.backup(archive)
    with zipfile.ZipFile(archive) as bundle:
        info = bundle.getinfo(asset.path)
        assert info.extract_version >= zipfile.ZIP64_VERSION
        assert info.compress_type == zipfile.ZIP_DEFLATED
        assert bundle.testzip() is None
    with closing(SQLiteProjectStore.restore(archive, tmp_path / "Копия")) as restored:
        assert restored.load() == store.load()
        assert (restored.root / asset.path).read_bytes() == source.read_bytes()


def test_restore_actual_enospc_leaves_archive_and_source_untouched(
    store, tmp_path, monkeypatch,
):
    archive = tmp_path / "copy.lodbackup"
    store.backup(archive)
    previous = store.path.read_bytes(), archive.read_bytes()
    target = tmp_path / "Копия"

    def fail_during_extraction(*args, **kwargs):
        raise OSError(errno.ENOSPC, "simulated disk full")

    monkeypatch.setattr(shutil, "copyfileobj", fail_during_extraction)
    with pytest.raises(OSError, match=sqlite_project_store.RESTORE_STAGE) as error:
        SQLiteProjectStore.restore(archive, target)
    assert str(target) in str(error.value) and "Требуется " in str(error.value)
    assert error.value.__cause__.errno == errno.ENOSPC
    assert not target.exists() and not tuple(tmp_path.glob(".lodandsy-restore-*"))
    assert (store.path.read_bytes(), archive.read_bytes()) == previous


def test_archive_enospc_after_creating_staging_preserves_previous_backup(
    store, tmp_path, monkeypatch,
):
    destination = tmp_path / "previous.lodbackup"
    store.backup(destination)
    before = store.path.read_bytes(), destination.read_bytes()
    write = zipfile.ZipFile.write

    def write_then_fail(bundle, *args, **kwargs):
        write(bundle, *args, **kwargs)
        raise OSError(errno.ENOSPC, "simulated archive write failure")

    monkeypatch.setattr(zipfile.ZipFile, "write", write_then_fail)
    with pytest.raises(OSError, match=sqlite_project_store.ARCHIVE_STAGE) as error:
        store.backup(destination)
    assert str(destination) in str(error.value) and error.value.__cause__.errno == errno.ENOSPC
    assert not tuple(tmp_path.glob("*.tmp"))
    assert (store.path.read_bytes(), destination.read_bytes()) == before
