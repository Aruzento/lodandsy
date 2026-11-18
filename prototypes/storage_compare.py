"""ARU-40: crash/recovery experiment in disposable local temporary directories.

No production format, migrations or application storage is implemented here.
The worker deliberately exits between writes, not during a power failure.
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

ENTITIES = [
    {"id": "a", "parent_id": None, "content": "A"},
    {"id": "b", "parent_id": "a", "content": "B"},
    {"id": "c", "parent_id": None, "content": "C"},
]


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read_json_entities(project):
    return [json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(project.glob("entity-*.json"))]


def has_orphans(entities):
    ids = {entity["id"] for entity in entities}
    return any(entity["parent_id"] is not None and entity["parent_id"] not in ids
               for entity in entities)


def connect(project):
    connection = sqlite3.connect(project / "world.db")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def worker(backend, project):
    project = project.resolve()
    if not (project.is_relative_to(Path(tempfile.gettempdir()).resolve())
            and project.parent.name.startswith("lodandsy-storage-prototype-")):
        raise ValueError("Worker may only alter its disposable prototype directory")
    if backend == "s1-journal":
        write_json(project / "pending-delete.json", ["a", "b"])
    if backend.startswith("s1"):
        (project / "entity-a.json").unlink()
        os._exit(17)
    connection = connect(project)
    connection.execute("BEGIN IMMEDIATE")
    connection.execute("DELETE FROM entity WHERE id='b'")
    os._exit(17)


def experiment(backend, project):
    project.mkdir()
    if backend.startswith("s1"):
        for entity in ENTITIES:
            write_json(project / f"entity-{entity['id']}.json", entity)
    else:
        with closing(connect(project)) as connection, connection:
            connection.execute(
                "CREATE TABLE entity(id TEXT PRIMARY KEY, parent_id TEXT REFERENCES entity(id), "
                "content TEXT NOT NULL)"
            )
            connection.executemany(
                "INSERT INTO entity VALUES(:id,:parent_id,:content)", ENTITIES
            )
    child = subprocess.run(
        [sys.executable, __file__, "--worker", backend, "--project", str(project)],
        check=False, capture_output=True,
    )
    assert child.returncode == 17, child.stderr.decode(errors="replace")
    if backend.startswith("s1"):
        interrupted = read_json_entities(project)
        result = {"after_crash_ids": [e["id"] for e in interrupted],
                  "orphan_after_crash": has_orphans(interrupted)}
        if backend == "s1-journal":
            journal = project / "pending-delete.json"
            pending = json.loads(journal.read_text(encoding="utf-8"))
            for entity_id in pending:
                (project / f"entity-{entity_id}.json").unlink(missing_ok=True)
            journal.unlink()
            recovered = read_json_entities(project)
            assert [e["id"] for e in recovered] == ["c"]
            assert not has_orphans(recovered)
            # A derived SQLite index can be rebuilt from canonical JSON.
            with closing(sqlite3.connect(project / "index.db")) as index, index:
                index.execute("CREATE TABLE entity(id TEXT PRIMARY KEY, content TEXT)")
                index.executemany("INSERT INTO entity VALUES(:id,:content)", recovered)
                assert index.execute("SELECT id FROM entity").fetchall() == [("c",)]
            result.update(recovered_ids=[e["id"] for e in recovered], index_rebuild=True)
        else:
            assert result["orphan_after_crash"]
        return result
    connection = connect(project)
    rows = connection.execute("SELECT id,parent_id,content FROM entity ORDER BY id").fetchall()
    assert rows == [(e["id"], e["parent_id"], e["content"]) for e in ENTITIES]
    assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    with connection:
        connection.execute("DELETE FROM entity WHERE id IN ('a','b')")
    with closing(sqlite3.connect(project / "backup.db")) as backup:
        connection.backup(backup)
        assert backup.execute("SELECT id FROM entity").fetchall() == [("c",)]
    connection.close()
    return {"after_crash_ids": [r[0] for r in rows], "rollback_complete": True,
            "committed_ids": ["c"], "database_backup_verified": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=["s1-naive", "s1-journal", "s3"])
    parser.add_argument("--project", type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.project)
    with tempfile.TemporaryDirectory(prefix="lodandsy-storage-prototype-") as temporary:
        root = Path(temporary).resolve()
        assert root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        results = {backend: experiment(backend, root / backend)
                   for backend in ["s1-naive", "s1-journal", "s3"]}
        print(json.dumps({"sqlite": sqlite3.sqlite_version, "results": results}, indent=2))


if __name__ == "__main__":
    main()
