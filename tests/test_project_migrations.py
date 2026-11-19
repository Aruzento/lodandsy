import hashlib
from contextlib import closing

import pytest

from lodandsy.application.sqlite_project_store import (
    SCHEMA_VERSION,
    ProjectError,
    SQLiteProjectStore,
    connect_database,
)


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
