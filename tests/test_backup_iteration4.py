import errno
import zipfile
from contextlib import closing

import pytest

from lodandsy.application.sqlite_project_store import (
    MAX_BACKUP_BYTES,
    ProjectError,
    SQLiteProjectStore,
    connect_database,
)
from tests.test_map_tokens_grid import open_map

pytest_plugins = ["tests.project_fixture"]


def test_new_inventory_integrity_checksum_limits_and_disk_error(
    project, qtbot, tmp_path, monkeypatch
):
    app, project = project
    doc, widget = open_map(app, project, tmp_path, qtbot)
    card = app.create_card("Imported metadata")
    app.cards_service.update_card_fields(
        card.id, {"mow_id": card.id, "mow_type": "creature", "hp": 0}
    )
    layer = app.maps_service.add_layer(doc.id, "Objects")
    app.maps_service.add_object(doc.id, layer.id, doc.asset_id, 10, 20)
    app.maps_service.add_token(doc.id, card.id, 30, 40)
    assert project.save_current()
    assert MAX_BACKUP_BYTES == 4 * 1024**3
    backup = tmp_path / "copy.lodbackup"
    project.store.backup(backup)
    with zipfile.ZipFile(backup) as archive:
        assert archive.testzip() is None
        assert all(n == "project.sqlite3" or n.startswith("assets/") for n in archive.namelist())
    restored = SQLiteProjectStore.restore(backup, tmp_path / "restore")
    with closing(connect_database(restored.path, readonly=True)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
    restored.close()
    with pytest.raises(ProjectError, match="new folder"):
        SQLiteProjectStore.restore(backup, tmp_path / "restore")
    original = backup.read_bytes()

    def no_space(*args, **kwargs):
        raise OSError(errno.ENOSPC, "No space left")

    with monkeypatch.context() as patch:
        patch.setattr(zipfile.ZipFile, "write", no_space)
        with pytest.raises(OSError):
            project.store.backup(backup)
    assert backup.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))
    with monkeypatch.context() as patch:
        patch.setattr("lodandsy.application.sqlite_project_store.MAX_BACKUP_BYTES", 1)
        with pytest.raises(ProjectError, match="4 GiB"):
            project.store.backup(tmp_path / "too-large.lodbackup")
        assert not (tmp_path / "too-large.lodbackup").exists()
    asset = project.assets[doc.asset_id]
    path = project.store.root / asset.path
    content = path.read_bytes()
    path.write_bytes(b"x" * len(content))
    with pytest.raises(ProjectError, match="checksum"):
        project.store.backup(tmp_path / "corrupt.lodbackup")
