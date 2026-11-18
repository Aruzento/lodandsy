import hashlib
import zipfile
from contextlib import closing
from dataclasses import replace
from uuid import UUID

import pytest

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
    cards.update(child.id, content="# Исходник\n\n**Markdown**\n\tTail  ")
    return cards, a, b, child


@pytest.mark.parametrize("path,checksum", [
    (b"assets/image.png", "0" * 64),
    ("assets/image.png", b"0" * 64),
    ("assets/image\0.png", "0" * 64),
])
def test_malformed_asset_values_are_diagnosed_without_rewriting_database(store, path, checksum):
    with closing(connect_database(store.path)) as connection, connection:
        connection.execute("INSERT INTO asset VALUES(?,?,?,?)",
                           (str(UUID(int=1)), path, checksum, 0))
    with pytest.raises(ProjectError, match="Invalid asset"):
        store.load()
    with closing(connect_database(store.path)) as connection:
        assert connection.execute("SELECT path,sha256 FROM asset").fetchone() == (path, checksum)


def test_create_save_close_reopen_preserves_ids_markdown_hierarchy_and_order(store):
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
        assert loaded.get(child.id).content == "# Исходник\n\n**Markdown**\n\tTail  "
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


@pytest.mark.parametrize("mutation", [
    "PRAGMA user_version=999",
    "UPDATE entity SET kind='future'",
    "UPDATE entity SET payload_version=999",
    "UPDATE entity SET parent_id=id",
    "UPDATE entity SET position=10",
])
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
    with pytest.raises(ProjectError, match="Cannot read"):
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


def test_backup_preserves_unregistered_assets_referenced_by_markdown(store, tmp_path):
    folder = store.root / "assets/user-images"
    folder.mkdir()
    (folder / "image.png").write_bytes(b"user image bytes")
    cards = CardCollection()
    card = cards.create("With image")
    cards.update_content(card.id, "![image](assets/user-images/image.png)")
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
    monkeypatch.setattr(
        "lodandsy.application.sqlite_project_store.uuid4", lambda: UUID(asset.id)
    )
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
