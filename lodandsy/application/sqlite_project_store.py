import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import zipfile
from contextlib import closing
from dataclasses import asdict, dataclass, field
from functools import wraps
from pathlib import Path, PurePosixPath
from uuid import uuid4

from lodandsy.application.card_payload_codec import decode_actor, decode_card, encode_card_aggregate
from lodandsy.application.fog_geometry import decode_fog
from lodandsy.application.table_column_codec import decode_column, encode_settings
from lodandsy.domain.card import Card, validate_card_id
from lodandsy.domain.card_collection import CardCollection
from lodandsy.domain.document_payloads import project_entities
from lodandsy.domain.entity import Entity
from lodandsy.domain.map_document import (
    MapDocument,
    MapGrid,
    MapLayer,
    MapPortal,
    MapShape,
    PlacedAssetObject,
    TokenInstance,
)
from lodandsy.domain.rules_5e14 import ProjectRules
from lodandsy.domain.table_document import RowRecord, TableDocument

DATABASE_NAME = "project.sqlite3"
SCHEMA_VERSION = 16
MAX_BACKUP_BYTES = 4 * 1024**3


class ProjectError(ValueError):
    pass


@dataclass(frozen=True)
class AssetRecord:
    id: str
    path: str
    sha256: str
    size: int

    def __post_init__(self):
        validate_card_id(self.id)
        if not isinstance(self.path, str) or "\0" in self.path:
            raise ProjectError("Invalid asset path")
        parts = PurePosixPath(self.path).parts
        if (
            len(parts) != 2
            or parts[0] != "assets"
            or "\\" in self.path
            or ":" in self.path
            or ".." in parts
        ):
            raise ProjectError("Asset path must be relative to assets/")
        if (
            not isinstance(self.sha256, str)
            or len(self.sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.sha256)
        ):
            raise ProjectError("Invalid asset checksum")
        if type(self.size) is not int or self.size < 0:
            raise ProjectError("Invalid asset size")


@dataclass(frozen=True)
class ProjectSnapshot:
    cards: tuple[Card, ...]
    revision: int
    assets: tuple[AssetRecord, ...] = ()
    maps: tuple[MapDocument, ...] = ()
    tables: tuple[TableDocument, ...] = ()
    entities: tuple[Entity, ...] = ()
    rules: ProjectRules = field(default_factory=ProjectRules)

    def entity_collection(self):
        return project_entities(
            self.cards, self.maps, self.tables, self.entities, settings=self.rules
        )

    def __post_init__(self):
        if not self.entities:
            object.__setattr__(self, "entities", self.entity_collection().summaries())


class ProjectLock:
    def __init__(self, root: Path):
        self._file = (root / ".lodandsy.lock").open("a+b")
        try:
            self._file.seek(0, os.SEEK_END)
            if self._file.tell() == 0:
                self._file.write(b"0")
                self._file.flush()
            self._file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._file.close()
            raise ProjectError("Project is already open or cannot be locked") from None

    def close(self):
        if not self._file.closed:
            self._file.close()


def connect_database(path: Path, *, readonly=False):
    connection = sqlite3.connect(
        path.as_uri() + ("?mode=ro" if readonly else "?mode=rw"), uri=True, timeout=5
    )
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    return connection


def project_operation(operation):
    @wraps(operation)
    def guarded(self, *args, **kwargs):
        with self._operation_lock:
            self._check_open()
            try:
                return operation(self, *args, **kwargs)
            except sqlite3.Error as error:
                raise ProjectError(f"Project {operation.__name__} failed: {error}") from error

    return guarded


class SQLiteProjectStore:
    """One writer lease; SQL and filesystem operations stay inside this adapter."""

    def __init__(self, root: Path, lock: ProjectLock):
        self.root = root
        self.path = root / DATABASE_NAME
        self._lock = lock
        self._closed = False
        self._operation_lock = threading.RLock()

    @classmethod
    def create(cls, folder: Path):
        root = Path(folder).resolve()
        root.mkdir(parents=True, exist_ok=True)
        if any(root.iterdir()):
            raise ProjectError("Create a project in an empty folder")
        lock = ProjectLock(root)
        store = cls(root, lock)
        try:
            with closing(sqlite3.connect(store.path)) as connection, connection:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute(
                    "CREATE TABLE metadata(name TEXT NOT NULL, revision INTEGER NOT NULL)"
                )
                connection.execute("INSERT INTO metadata VALUES(?, 0)", (root.name,))
                connection.execute(
                    "CREATE TABLE entity(id TEXT PRIMARY KEY, kind TEXT NOT NULL, "
                    "title TEXT NOT NULL, parent_id TEXT REFERENCES entity(id) "
                    "DEFERRABLE INITIALLY DEFERRED, position INTEGER NOT NULL CHECK(position>=0))"
                )
                connection.execute(
                    "CREATE TABLE asset(id TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, "
                    "sha256 TEXT NOT NULL, size INTEGER NOT NULL CHECK(size>=0))"
                )
                connection.execute(
                    "CREATE INDEX entity_parent_position ON entity(parent_id,position)"
                )
                connection.execute(
                    "CREATE TABLE card_content(id TEXT PRIMARY KEY "
                    "REFERENCES entity(id) ON DELETE CASCADE, "
                    "payload_version INTEGER NOT NULL, content TEXT NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE map_document(id TEXT PRIMARY KEY "
                    "REFERENCES entity(id) ON DELETE CASCADE, asset_id TEXT NOT NULL "
                    "REFERENCES asset(id) DEFERRABLE INITIALLY DEFERRED, "
                    "payload_version INTEGER NOT NULL, "
                    "grid TEXT NOT NULL, "
                    "layers TEXT NOT NULL, objects TEXT NOT NULL, "
                    "layers_initialized INTEGER NOT NULL CHECK(layers_initialized IN (0,1)), "
                    "fog TEXT NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE table_document(id TEXT PRIMARY KEY "
                    "REFERENCES entity(id) ON DELETE CASCADE, "
                    "payload_version INTEGER NOT NULL)"
                )
                connection.executescript("""
                    CREATE TABLE card_actor(
                      id TEXT PRIMARY KEY, card_id TEXT NOT NULL REFERENCES card_content(id)
                        DEFERRABLE INITIALLY DEFERRED,
                      inventory_id TEXT UNIQUE REFERENCES table_document(id)
                        DEFERRABLE INITIALLY DEFERRED,
                      payload_version INTEGER NOT NULL, state TEXT NOT NULL,
                      UNIQUE(card_id,id));
                    CREATE TABLE card_default_actor(
                      card_id TEXT PRIMARY KEY REFERENCES card_content(id),
                      actor_id TEXT NOT NULL,
                      FOREIGN KEY(card_id,actor_id) REFERENCES card_actor(card_id,id)
                        DEFERRABLE INITIALLY DEFERRED);
                    CREATE TABLE map_token(
                      id TEXT PRIMARY KEY, map_id TEXT NOT NULL REFERENCES map_document(id)
                        DEFERRABLE INITIALLY DEFERRED,
                      ordinal INTEGER NOT NULL CHECK(ordinal>=0),
                      card_id TEXT NOT NULL REFERENCES card_content(id)
                        DEFERRABLE INITIALLY DEFERRED,
                      actor_id TEXT, placement TEXT NOT NULL,
                      UNIQUE(map_id,ordinal),
                      FOREIGN KEY(card_id,actor_id) REFERENCES card_actor(card_id,id)
                        DEFERRABLE INITIALLY DEFERRED);
                    CREATE INDEX token_actor ON map_token(actor_id);
                    CREATE TABLE project_rules(
                      id INTEGER PRIMARY KEY CHECK(id=1), payload_version INTEGER NOT NULL,
                      ruleset TEXT NOT NULL, rules_version INTEGER NOT NULL,
                      revision INTEGER NOT NULL, overrides TEXT NOT NULL);
                    INSERT INTO project_rules VALUES(1,1,'dnd_5e_2014',2,0,'[]');
                    CREATE TABLE table_column(
                      id TEXT PRIMARY KEY, table_id TEXT NOT NULL REFERENCES table_document(id),
                      name TEXT NOT NULL, data_type TEXT NOT NULL, position INTEGER NOT NULL,
                      settings TEXT NOT NULL,
                      UNIQUE(table_id,id), UNIQUE(table_id,position));
                    CREATE TABLE table_row(
                      id TEXT PRIMARY KEY, table_id TEXT NOT NULL REFERENCES table_document(id),
                      position INTEGER NOT NULL, UNIQUE(table_id,id), UNIQUE(table_id,position));
                    CREATE TABLE table_cell(
                      table_id TEXT NOT NULL, row_id TEXT NOT NULL, column_id TEXT NOT NULL,
                      value TEXT NOT NULL, PRIMARY KEY(table_id,row_id,column_id),
                      FOREIGN KEY(table_id,row_id) REFERENCES table_row(table_id,id),
                      FOREIGN KEY(table_id,column_id) REFERENCES table_column(table_id,id));
                """)
                connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            (root / "assets").mkdir()
        except sqlite3.Error as error:
            store.close()
            raise ProjectError(f"Cannot create project: {error}") from error
        except Exception:
            store.close()
            raise
        return store

    @classmethod
    def open(cls, folder: Path):
        root = Path(folder).resolve()
        if not (root / DATABASE_NAME).is_file():
            raise ProjectError(f"No {DATABASE_NAME} in the selected folder")
        store = cls(root, ProjectLock(root))
        try:
            store.load()
        except Exception:
            store.close()
            raise
        return store

    def _check_open(self):
        if self._closed:
            raise ProjectError("Project has been closed")

    @project_operation
    def load(self) -> ProjectSnapshot:
        self._check_open()
        try:
            with closing(connect_database(self.path, readonly=True)) as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version != SCHEMA_VERSION:
                    raise ProjectError(f"Unsupported project schema version: {version}")
                if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise ProjectError("Project database is damaged; restore a backup")
                if connection.execute("PRAGMA foreign_key_check").fetchall():
                    raise ProjectError("Project hierarchy contains missing parents")
                metadata = connection.execute("SELECT revision FROM metadata").fetchall()
                if len(metadata) != 1 or type(metadata[0][0]) is not int or metadata[0][0] < 0:
                    raise ProjectError("Invalid project metadata")
                assets = tuple(
                    AssetRecord(*row)
                    for row in connection.execute(
                        "SELECT id,path,sha256,size FROM asset ORDER BY id"
                    )
                )
                envelopes = tuple(
                    Entity(*row)
                    for row in connection.execute(
                        "SELECT id,kind,title,parent_id,position FROM entity ORDER BY position,id"
                    )
                )
                actor_rows = {}
                for key, owner, inventory_id, version, state in connection.execute(
                    "SELECT id,card_id,inventory_id,payload_version,state "
                    "FROM card_actor ORDER BY id"
                ):
                    actor_rows.setdefault(owner, []).append(
                        decode_actor(key, inventory_id, version, state)
                    )
                defaults = dict(
                    connection.execute("SELECT card_id,actor_id FROM card_default_actor")
                )
                rules_rows = connection.execute(
                    "SELECT payload_version,ruleset,rules_version,revision,overrides "
                    "FROM project_rules"
                ).fetchall()
                if len(rules_rows) != 1 or rules_rows[0][0] != 1:
                    raise ProjectError("Unsupported project rules payload")
                _, ruleset, rules_version, rules_revision, overrides = rules_rows[0]
                decoded_overrides = json.loads(overrides)
                if not isinstance(decoded_overrides, list):
                    raise ProjectError("Invalid rules overrides")
                rules = ProjectRules(
                    ruleset,
                    rules_version,
                    rules_revision,
                    tuple(tuple(pair) for pair in decoded_overrides),
                )
                cards = tuple(
                    decode_card(
                        title,
                        key,
                        parent,
                        payload_version,
                        content,
                        actors=tuple(actor_rows.get(key, ())),
                        default_actor_id=defaults.get(key),
                    )
                    for key, title, parent, payload_version, content in connection.execute(
                        "SELECT e.id,e.title,e.parent_id,c.payload_version,c.content "
                        "FROM entity e JOIN card_content c ON e.id=c.id WHERE e.kind='card'"
                    )
                )
                maps, tables = self._load_modules(connection)
                snapshot = ProjectSnapshot(
                    tuple(cards), metadata[0][0], assets, maps, tables, envelopes, rules
                )
                collection = snapshot.entity_collection()
                ordered_cards = CardCollection(entities=collection).all()
                self._validate_modules(ordered_cards, assets, maps, tables)
                expected = {
                    "card": "card_content",
                    "map": "map_document",
                    "table": "table_document",
                }
                for kind, table in expected.items():
                    ids = {row[0] for row in connection.execute(f"SELECT id FROM {table}")}
                    if ids != {e.id for e in envelopes if e.kind == kind}:
                        raise ProjectError("Entity payload inventory mismatch")
                return ProjectSnapshot(
                    ordered_cards,
                    metadata[0][0],
                    assets,
                    maps,
                    tables,
                    collection.summaries(),
                    rules,
                )
        except sqlite3.Error as error:
            raise ProjectError(f"Cannot read project: {error}") from error
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            if isinstance(error, ProjectError):
                raise
            raise ProjectError(f"Cannot read project: {error}") from error

    @staticmethod
    def _require_version(actual, expected, kind):
        if type(actual) is not int or actual != expected:
            raise ProjectError(f"Unsupported {kind} payload version: {actual}")
        return True

    @staticmethod
    def _load_modules(connection):
        maps, tables = [], []
        try:
            token_rows = {}
            for key, map_id, ordinal, card_id, actor_id, placement in connection.execute(
                "SELECT id,map_id,ordinal,card_id,actor_id,placement FROM map_token "
                "ORDER BY map_id,ordinal"
            ):
                entries = token_rows.setdefault(map_id, [])
                if ordinal != len(entries):
                    raise ValueError("Non-contiguous token order")
                values = json.loads(placement)
                if not isinstance(values, dict) or values.keys() != {
                    "x",
                    "y",
                    "cells_w",
                    "cells_h",
                    "z",
                    "label_override",
                    "image_override",
                    "kind_override",
                    "layer_id",
                }:
                    raise ValueError("Invalid Token placement fields")
                entries.append(TokenInstance(card_id, id=key, actor_id=actor_id, **values))
            for (
                key,
                title,
                asset,
                version,
                grid,
                layers,
                objects,
                initialized,
                fog,
            ) in connection.execute(
                "SELECT m.id,e.title,m.asset_id,m.payload_version,"
                "m.grid,m.layers,m.objects,m.layers_initialized,m.fog "
                "FROM map_document m JOIN entity e ON e.id=m.id ORDER BY e.position,e.id"
            ):
                if version not in (7, 8, 9):
                    raise ValueError("Unsupported Map version")
                vector_data = json.loads(objects)
                if version == 7:
                    vector_data = {"objects": vector_data, "shapes": [], "portals": []}
                if not isinstance(vector_data, dict) or set(vector_data) != {
                    "objects",
                    "shapes",
                    "portals",
                }:
                    raise ValueError("Invalid map vectors")
                grid = json.loads(grid)
                if not isinstance(grid, dict):
                    raise ValueError("Invalid map payload")
                maps.append(
                    MapDocument(
                        title,
                        asset,
                        key,
                        tuple(token_rows.get(key, ())),
                        MapGrid(**grid),
                        tuple(MapLayer(**layer) for layer in json.loads(layers)),
                        tuple(PlacedAssetObject(**o) for o in vector_data["objects"]),
                        bool(initialized),
                        decode_fog(fog),
                        tuple(
                            MapShape(**dict(v, points=tuple(tuple(p) for p in v["points"])))
                            for v in vector_data["shapes"]
                        ),
                        tuple(MapPortal(**v) for v in vector_data["portals"]),
                    )
                )
            columns, rows, cells = {}, {}, {}
            for key, table_id, name, data_type, position, settings in connection.execute(
                "SELECT id,table_id,name,data_type,position,settings "
                "FROM table_column ORDER BY position"
            ):
                columns.setdefault(table_id, []).append(
                    decode_column(name, data_type, position, key, settings)
                )
            for table_id, row_id, column_id, value in connection.execute(
                "SELECT table_id,row_id,column_id,value FROM table_cell ORDER BY column_id"
            ):
                cells.setdefault((table_id, row_id), []).append((column_id, json.loads(value)))
            for key, table_id, position in connection.execute(
                "SELECT id,table_id,position FROM table_row ORDER BY position"
            ):
                rows.setdefault(table_id, []).append(
                    RowRecord(position, tuple(cells.get((table_id, key), ())), key)
                )
            for key, title, version in connection.execute(
                "SELECT t.id,e.title,t.payload_version FROM table_document t "
                "JOIN entity e ON e.id=t.id ORDER BY e.position,e.id"
            ):
                SQLiteProjectStore._require_version(version, 3, "Table")
                tables.append(
                    TableDocument(title, key, tuple(columns.get(key, ())), tuple(rows.get(key, ())))
                )
        except (TypeError, KeyError, ValueError) as error:
            raise ProjectError(f"Cannot read module data: {error}") from error
        return tuple(maps), tuple(tables)

    @staticmethod
    def _validate_modules(cards, assets, maps, tables):
        ids = [item.id for item in (*cards, *maps, *tables)]
        if len(ids) != len(set(ids)):
            raise ProjectError("Duplicate entity ID across modules")
        asset_ids = {asset.id for asset in assets}
        if any(document.asset_id not in asset_ids for document in maps):
            raise ProjectError("Map refers to an unregistered asset")

    @project_operation
    def save(self, snapshot: ProjectSnapshot):
        self._check_open()
        collection = snapshot.entity_collection()
        cards = CardCollection(entities=collection).all()
        if type(snapshot.revision) is not int or snapshot.revision < 0:
            raise ProjectError("Invalid snapshot revision")
        assets = {asset.id: asset for asset in snapshot.assets}
        if len(assets) != len(snapshot.assets):
            raise ProjectError("Duplicate asset ID")
        self._validate_modules(cards, snapshot.assets, snapshot.maps, snapshot.tables)
        with closing(connect_database(self.path)) as connection, connection:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                raise ProjectError("Project schema changed; save refused")
            # Refuse to overwrite unsupported/corrupt existing data, including payload inventory.
            self.load()
            current = connection.execute("SELECT revision FROM metadata").fetchone()[0]
            if snapshot.revision <= current:
                raise ProjectError("Stale revision cannot overwrite a newer project")
            # Validate existing module versions before replacing any canonical payload.
            self._load_modules(connection)
            existing_assets = {
                row[0]: AssetRecord(*row)
                for row in connection.execute("SELECT id,path,sha256,size FROM asset")
            }
            for asset in snapshot.assets:
                if existing_assets.get(asset.id) != asset:
                    self._verify_asset(asset)
            card_parts = [(c, encode_card_aggregate(c)) for c in cards]
            encoded_cards = [(c.id, parts[0], parts[1]) for c, parts in card_parts]
            for table in (
                "table_cell",
                "table_row",
                "table_column",
                "map_token",
                "card_default_actor",
                "card_actor",
                "card_content",
                "map_document",
                "table_document",
            ):
                connection.execute(f"DELETE FROM {table}")
            connection.execute("DELETE FROM entity")
            connection.execute("DELETE FROM asset")
            connection.executemany(
                "INSERT INTO asset VALUES(?,?,?,?)",
                [(a.id, a.path, a.sha256, a.size) for a in snapshot.assets],
            )
            connection.executemany(
                "INSERT INTO entity VALUES(?,?,?,?,?)",
                [(e.id, e.kind, e.title, e.parent_id, e.position) for e in collection.summaries()],
            )
            connection.executemany("INSERT INTO card_content VALUES(?,?,?)", encoded_cards)
            connection.executemany(
                "INSERT INTO map_document VALUES(?,?,?,?,?,?,?,?)",
                [
                    (
                        m.id,
                        m.asset_id,
                        9,
                        json.dumps(asdict(m.grid)),
                        json.dumps([asdict(layer) for layer in m.layers], ensure_ascii=False),
                        json.dumps(
                            {
                                "objects": [asdict(o) for o in m.objects],
                                "shapes": [asdict(v) for v in m.shapes],
                                "portals": [asdict(v) for v in m.portals],
                            },
                            ensure_ascii=False,
                        ),
                        int(m.layers_initialized),
                        json.dumps([asdict(r) for r in m.fog.regions]),
                    )
                    for m in snapshot.maps
                ],
            )
            connection.executemany(
                "INSERT INTO table_document VALUES(?,?)",
                [(t.id, 3) for t in snapshot.tables],
            )
            connection.executemany(
                "INSERT INTO card_actor VALUES(?,?,?,?,?)",
                [row for card, parts in card_parts for row in parts[2]],
            )
            connection.executemany(
                "INSERT INTO card_default_actor VALUES(?,?)",
                [(card.id, parts[3]) for card, parts in card_parts if parts[3] is not None],
            )
            connection.executemany(
                "INSERT INTO map_token VALUES(?,?,?,?,?,?)",
                [
                    (
                        token.id,
                        document.id,
                        ordinal,
                        token.card_id,
                        token.actor_id,
                        json.dumps(
                            {
                                k: v
                                for k, v in asdict(token).items()
                                if k not in {"id", "card_id", "actor_id"}
                            },
                            ensure_ascii=False,
                        ),
                    )
                    for document in snapshot.maps
                    for ordinal, token in enumerate(document.tokens)
                ],
            )
            connection.executemany(
                "INSERT INTO table_column VALUES(?,?,?,?,?,?)",
                [
                    (c.id, t.id, c.name, c.data_type, c.position, encode_settings(c))
                    for t in snapshot.tables
                    for c in t.columns
                ],
            )
            connection.executemany(
                "INSERT INTO table_row VALUES(?,?,?)",
                [(r.id, t.id, r.position) for t in snapshot.tables for r in t.rows],
            )
            connection.executemany(
                "INSERT INTO table_cell VALUES(?,?,?,?)",
                [
                    (t.id, r.id, key, json.dumps(value, ensure_ascii=False))
                    for t in snapshot.tables
                    for r in t.rows
                    for key, value in r.cells
                ],
            )
            connection.execute("UPDATE metadata SET revision=?", (snapshot.revision,))
            connection.execute(
                "UPDATE project_rules SET ruleset=?,rules_version=?,revision=?,overrides=? "
                "WHERE id=1",
                (
                    snapshot.rules.ruleset,
                    snapshot.rules.version,
                    snapshot.rules.revision,
                    json.dumps(snapshot.rules.overrides, ensure_ascii=False),
                ),
            )

    @project_operation
    def import_asset(
        self, source: Path, *, known_assets=(), max_bytes=None, cancelled=lambda: False
    ) -> AssetRecord:
        self._check_open()
        source = Path(source)
        suffix = source.suffix.lower()
        if len(suffix) > 12 or not suffix[1:].isalnum():
            suffix = ".bin"
        asset_id = str(uuid4())
        with closing(connect_database(self.path, readonly=True)) as connection:
            duplicate = connection.execute("SELECT 1 FROM asset WHERE id=?", (asset_id,)).fetchone()
        if duplicate or any((self.root / "assets").glob(f"{asset_id}.*")):
            raise ProjectError("Asset ID collision; existing resource preserved")
        relative = f"assets/{asset_id}{suffix}"
        target = self.root / relative
        target.parent.mkdir(exist_ok=True)
        if not target.resolve().is_relative_to(self.root):
            raise ProjectError("Asset directory is outside the project")
        temporary = target.with_suffix(target.suffix + ".tmp")
        checksum, size = hashlib.sha256(), 0
        try:
            with source.open("rb") as incoming, temporary.open("xb") as outgoing:
                for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
                    if cancelled():
                        raise ProjectError("Импорт ресурса отменён")
                    if max_bytes is not None and size + len(chunk) > max_bytes:
                        raise ProjectError("Asset exceeds import size limit")
                    outgoing.write(chunk)
                    checksum.update(chunk)
                    size += len(chunk)
                outgoing.flush()
                os.fsync(outgoing.fileno())
            for existing in known_assets:
                if existing.sha256 == checksum.hexdigest() and existing.size == size:
                    try:
                        self._verify_asset(existing)
                    except OSError, ValueError:
                        continue
                    return existing
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return AssetRecord(asset_id, relative, checksum.hexdigest(), size)

    def _verify_asset(self, asset):
        path = self.root / asset.path
        if not path.resolve().is_relative_to(self.root):
            raise ProjectError("Asset path is outside the project")
        if not path.is_file() or path.stat().st_size != asset.size:
            raise ProjectError(f"Missing or incomplete asset: {asset.path}")
        checksum = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                checksum.update(chunk)
        if checksum.hexdigest() != asset.sha256:
            raise ProjectError(f"Asset checksum mismatch: {asset.path}")

    @project_operation
    def backup(self, destination: Path):
        self._check_open()
        destination = Path(destination).resolve()
        if destination.is_relative_to(self.root):
            raise ProjectError("Save backups outside the project folder")
        with tempfile.TemporaryDirectory(prefix="lodandsy-backup-") as temporary:
            staging = Path(temporary).resolve()
            assert staging.is_relative_to(Path(tempfile.gettempdir()).resolve())
            database = staging / DATABASE_NAME
            with closing(connect_database(self.path, readonly=True)) as source:
                with closing(sqlite3.connect(database)) as backup:
                    backup.execute("PRAGMA foreign_keys=ON")
                    source.backup(backup)
                    assets = tuple(
                        AssetRecord(*row)
                        for row in backup.execute("SELECT id,path,sha256,size FROM asset")
                    )
            total = database.stat().st_size + sum(asset.size for asset in assets)
            if total > MAX_BACKUP_BYTES:
                raise ProjectError("Backup exceeds the supported 4 GiB restore budget")
            archive = destination.with_name(destination.name + f".{uuid4().hex}.tmp")
            try:
                with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
                    bundle.write(database, DATABASE_NAME)
                    registered_paths = {asset.path for asset in assets}
                    for asset in assets:
                        self._verify_asset(asset)
                        checksum, size = hashlib.sha256(), 0
                        with (self.root / asset.path).open("rb") as source:
                            with bundle.open(asset.path, "w") as output:
                                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                                    output.write(chunk)
                                    checksum.update(chunk)
                                    size += len(chunk)
                        if checksum.hexdigest() != asset.sha256 or size != asset.size:
                            raise ProjectError("Asset changed while creating backup")
                    # Documents may reference user-supplied files inside assets too.
                    # Preserve them, including unreferenced imports; never discard bytes
                    # merely because a derivative/infrastructure record is absent.
                    asset_folder = self.root / "assets"
                    if not asset_folder.resolve().is_relative_to(self.root):
                        raise ProjectError("Asset directory is outside the project")
                    for path in sorted(asset_folder.rglob("*")):
                        if not path.is_file():
                            continue
                        relative = path.relative_to(self.root).as_posix()
                        if relative in registered_paths:
                            continue
                        if not path.resolve().is_relative_to(asset_folder.resolve()):
                            raise ProjectError("Asset path is outside the project")
                        total += path.stat().st_size
                        if total > MAX_BACKUP_BYTES:
                            raise ProjectError("Backup exceeds the supported 4 GiB restore budget")
                        bundle.write(path, relative)
                    if sum(entry.file_size for entry in bundle.infolist()) > MAX_BACKUP_BYTES:
                        raise ProjectError("Backup grew beyond the supported 4 GiB restore budget")
                with archive.open("r+b") as stream:
                    os.fsync(stream.fileno())
                os.replace(archive, destination)
            finally:
                archive.unlink(missing_ok=True)

    @classmethod
    def restore(cls, archive: Path, destination: Path):
        destination = Path(destination).resolve()
        if destination.exists():
            raise ProjectError("Restore requires a new folder; existing data is never overwritten")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".lodandsy-restore-", dir=destination.parent
        ) as temp:
            staging = Path(temp).resolve()
            assert staging.parent == destination.parent
            with zipfile.ZipFile(archive) as bundle:
                entries = bundle.infolist()
                names = [entry.filename for entry in entries]
                if len(set(names)) != len(names) or DATABASE_NAME not in names:
                    raise ProjectError("Invalid backup inventory")
                if sum(entry.file_size for entry in entries) > MAX_BACKUP_BYTES:
                    raise ProjectError("Backup exceeds the 4 GiB restore limit")
                for entry in entries:
                    parts = PurePosixPath(entry.filename).parts
                    allowed = entry.filename == DATABASE_NAME or (
                        len(parts) >= 2 and parts[0] == "assets"
                    )
                    if (
                        not allowed
                        or ".." in parts
                        or "\\" in entry.filename
                        or ":" in entry.filename
                        or entry.is_dir()
                        or (entry.external_attr >> 16) & 0o170000 == 0o120000
                    ):
                        raise ProjectError("Unsafe backup entry")
                    target = staging / entry.filename
                    if not target.resolve().is_relative_to(staging):
                        raise ProjectError("Unsafe backup path")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(entry) as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output)
            validation = cls.open(staging)
            try:
                snapshot = validation.load()
                for asset in snapshot.assets:
                    validation._verify_asset(asset)
            finally:
                validation.close()
            staging.rename(destination)
        return cls.open(destination)

    def close(self):
        with self._operation_lock:
            if not self._closed:
                self._closed = True
                self._lock.close()
