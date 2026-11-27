import errno
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import threading
import zipfile
from contextlib import ExitStack, closing, contextmanager
from dataclasses import asdict, dataclass, field, replace
from functools import wraps
from pathlib import Path, PurePosixPath
from uuid import uuid4

from lodandsy.application.card_payload_codec import decode_actor, decode_card, encode_card_aggregate
from lodandsy.application.economy_codec import (
    ECONOMY_VERSION,
    decode_economy,
    decode_wallet,
    encode_economy,
    encode_wallet,
)
from lodandsy.application.fog_geometry import decode_fog
from lodandsy.application.table_column_codec import decode_column, encode_settings
from lodandsy.domain.card import Card, validate_card_id
from lodandsy.domain.card_collection import CardCollection
from lodandsy.domain.currency import CurrencySystem
from lodandsy.domain.document_payloads import project_entities
from lodandsy.domain.entity import Entity, EntityCollection
from lodandsy.domain.item_categories import ItemCategory
from lodandsy.domain.map_document import (
    MapDocument,
    MapGrid,
    MapLayer,
    MapPortal,
    MapShape,
    PlacedAssetObject,
    TokenInstance,
)
from lodandsy.domain.module_values import validate_id
from lodandsy.domain.project_settings import ProjectSettings
from lodandsy.domain.rules_5e14 import ProjectRules
from lodandsy.domain.table_document import RowRecord, TableDocument

DATABASE_NAME = "project.sqlite3"
LOCK_NAME = ".lodandsy.lock"
SCHEMA_VERSION = 17
MAX_BACKUP_BYTES = 4 * 1024**3
TEMP_DB_STAGE = "Создание временной SQLite"
ARCHIVE_STAGE = "Создание резервного архива"
RESTORE_STAGE = "Восстановление резервной копии"
VERIFY_STAGE = "Пробное восстановление Map10"
TRANSFORM_MAP_VERSION = 10
TOKEN_FIELDS = {
    "x", "y", "cells_w", "cells_h", "z", "label_override", "image_override", "kind_override",
    "layer_id",
}


class ProjectError(ValueError):
    pass


class IncompatibleProjectError(ProjectError):
    def __init__(self, version):
        self.version = version
        super().__init__(
            f"Unsupported project schema version: {version}. "
            f"Требуется SQLite-схема {SCHEMA_VERSION}."
        )


@dataclass(frozen=True)
class ProjectMetadata:
    project_id: str
    schema_version: int
    database_identity: tuple[int, int]


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
    currency: CurrencySystem = field(default_factory=CurrencySystem)
    custom_categories: tuple[ItemCategory, ...] = ()

    def entity_collection(self):
        return project_entities(
            self.cards, self.maps, self.tables, self.entities,
            settings=ProjectSettings(self.rules, self.currency, self.custom_categories),
        )

    def __post_init__(self):
        if not self.entities:
            object.__setattr__(self, "entities", self.entity_collection().summaries())


@dataclass(frozen=True)
class VerifiedProject:
    snapshot: ProjectSnapshot
    entities: EntityCollection
    map_versions: dict[str, int]


@dataclass(frozen=True)
class StoredRevision:
    snapshot: ProjectSnapshot
    map_versions: dict[str, int]
    payloads: dict[str, object]
    acknowledged_base: int | None = None

    @classmethod
    def verified(cls, snapshot, map_versions, collection, *, acknowledged_base=None):
        return cls(
            snapshot, map_versions, {e.id: collection.payload(e.id) for e in snapshot.entities},
            acknowledged_base,
        )

    def matches(self, snapshot, map_versions):
        previous = self.snapshot
        return (
            previous.revision == snapshot.revision
            and previous.rules == snapshot.rules
            and previous.currency == snapshot.currency
            and previous.custom_categories == snapshot.custom_categories
            and self.map_versions == map_versions
            and all(
                before == after or (
                    len(before) == len(after)
                    and {value.id: value for value in before}
                    == {value.id: value for value in after}
                )
                for before, after in (
                    (previous.entities, snapshot.entities),
                    (previous.cards, snapshot.cards), (previous.maps, snapshot.maps),
                    (previous.tables, snapshot.tables), (previous.assets, snapshot.assets),
                )
            )
        )


def _disk_full(error):
    if isinstance(error, OSError):
        return error.errno == errno.ENOSPC or getattr(error, "winerror", None) in {39, 112}
    code = getattr(error, "sqlite_errorcode", 0) or 0
    return (code & 0xFF) == sqlite3.SQLITE_FULL or "database or disk is full" in str(error)


class ProjectLock:
    def __init__(self, root: Path, filename=LOCK_NAME):
        self._file = (root / filename).open("a+b")
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
        except OSError as error:
            self._file.close()
            if _disk_full(error):
                raise
            raise ProjectError("Project is already open or cannot be locked") from None

    def close(self):
        if not self._file.closed:
            self._file.close()


def connect_database(path: Path, *, readonly=False):
    options = "?mode=ro" if readonly else "?mode=rw"
    connection = sqlite3.connect(
        path.as_uri() + options, uri=True, timeout=5
    )
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    return connection


def _space_message(path, stage, required):
    return f"Недостаточно свободного места. {stage}. Путь {path}. Требуется {required} байт."


def _require_space(directory, stage, required):
    free = shutil.disk_usage(directory).free
    if free < required:
        raise ProjectError(f"{_space_message(directory, stage, required)} Доступно {free} байт.")


@contextmanager
def _disk_stage(path, stage, required):
    try:
        yield
    except (OSError, sqlite3.Error) as error:
        if _disk_full(error):
            message = _space_message(path, stage, required)
            if isinstance(error, OSError):
                raise OSError(errno.ENOSPC, message) from error
            raise ProjectError(message) from error
        raise


def _volume_identity(directory):
    return directory.stat().st_dev or directory.anchor.casefold()


def _archive_requirement(entries):
    # DEFLATE can expand incompressible data. Allow 6.25% and room for local,
    # central and ZIP64 headers, including two copies of each UTF-8 name.
    return 128 + sum(
        size + size // 16 + 256 + 2 * len(name.encode("utf-8"))
        for name, size in entries
    )


def _preflight_backup(
    temporary, destination, sqlite_bytes, archive_bytes, total, verification_root,
):
    _require_space(temporary, TEMP_DB_STAGE, sqlite_bytes)
    target_volume = _volume_identity(destination)
    shared = _volume_identity(temporary) == target_volume
    _require_space(destination, ARCHIVE_STAGE, archive_bytes + (sqlite_bytes if shared else 0))
    if verification_root is not None:
        shared = _volume_identity(verification_root) == target_volume
        _require_space(
            verification_root, VERIFY_STAGE, total + (archive_bytes if shared else 0),
        )


def _publish_project(staging, destination):
    if os.name == "nt":
        # Windows rename is atomic and refuses an existing destination, including empty folders.
        staging.rename(destination)
        return
    # On Unix, rename may replace an empty directory. Reserve the name ourselves first.
    destination.mkdir()
    reserved = destination.stat()
    try:
        staging.rename(destination)
    except OSError:
        try:
            if os.path.samestat(reserved, destination.lstat()):
                destination.rmdir()
        except OSError:
            pass
        raise


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


def _entity_delta(before, after, rewrite_all):
    old = {e.id: e.kind for e in before.snapshot.entities}
    new = {e.id: e.kind for e in after.summaries()}
    removed = {kind: set() for kind in ("card", "map", "table")}
    changed = {kind: set() for kind in removed}
    for key, kind in old.items():
        if rewrite_all or new.get(key) != kind:
            removed[kind].add(key)
    for key, kind in new.items():
        if rewrite_all or old.get(key) != kind or before.payloads[key] != after.payload(key):
            changed[kind].add(key)
    return removed, changed


def _map_write_version(document, previous, changed):
    if not changed and previous is not None:
        return previous
    if previous == TRANSFORM_MAP_VERSION or any(
        token.uses_object_transform for token in document.tokens
    ):
        return TRANSFORM_MAP_VERSION
    return 9


def _write_cards(connection, cards):
    for card in cards:
        version, definition, actors, default = encode_card_aggregate(card)
        connection.execute(
            "INSERT INTO card_content VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "payload_version=excluded.payload_version,content=excluded.content",
            (card.id, version, definition),
        )
        connection.executemany("INSERT INTO card_actor VALUES(?,?,?,?,?)", actors)
        if default is not None:
            connection.execute("INSERT INTO card_default_actor VALUES(?,?)", (card.id, default))


def _write_maps(connection, maps, versions):
    for document in maps:
        version = versions[document.id]
        connection.execute(
            "INSERT INTO map_document VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "asset_id=excluded.asset_id,payload_version=excluded.payload_version,"
            "grid=excluded.grid,layers=excluded.layers,objects=excluded.objects,"
            "layers_initialized=excluded.layers_initialized,fog=excluded.fog",
            (
                document.id, document.asset_id, version,
                json.dumps(asdict(document.grid)),
                json.dumps([asdict(layer) for layer in document.layers], ensure_ascii=False),
                json.dumps(
                    {
                        "objects": [asdict(o) for o in document.objects],
                        "shapes": [asdict(v) for v in document.shapes],
                        "portals": [asdict(v) for v in document.portals],
                    },
                    ensure_ascii=False,
                ),
                int(document.layers_initialized),
                json.dumps([asdict(r) for r in document.fog.regions]),
            ),
        )
        fields = TOKEN_FIELDS | {"rotation"} if version == TRANSFORM_MAP_VERSION else TOKEN_FIELDS
        connection.executemany(
            "INSERT INTO map_token VALUES(?,?,?,?,?,?)",
            (
                (
                    t.id, document.id, ordinal, t.card_id, t.actor_id,
                    json.dumps(
                        {k: v for k, v in asdict(t).items() if k in fields}, ensure_ascii=False,
                    ),
                )
                for ordinal, t in enumerate(document.tokens)
            ),
        )


def _write_tables(connection, tables):
    for table in tables:
        connection.execute(
            "INSERT INTO table_document VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "payload_version=excluded.payload_version,wallet=excluded.wallet",
            (table.id, 4, encode_wallet(table.wallet)),
        )
        connection.executemany(
            "INSERT INTO table_column VALUES(?,?,?,?,?,?)",
            (
                (c.id, table.id, c.name, c.data_type, c.position, encode_settings(c))
                for c in table.columns
            ),
        )
        connection.executemany(
            "INSERT INTO table_row VALUES(?,?,?)",
            ((row.id, table.id, row.position) for row in table.rows),
        )
        connection.executemany(
            "INSERT INTO table_cell VALUES(?,?,?,?)",
            (
                (table.id, row.id, key, json.dumps(value, ensure_ascii=False))
                for row in table.rows for key, value in row.cells
            ),
        )


class SQLiteProjectStore:
    """One writer lease; SQL and filesystem operations stay inside this adapter."""

    def __init__(self, root: Path, lock: ProjectLock):
        self.root = root
        self.path = root / DATABASE_NAME
        self._lock = lock
        self._closed = False
        self._project_id = None
        self._file_identity = None
        self._stored = None
        self._pending = None
        self._operation_lock = threading.RLock()

    @classmethod
    def create(cls, folder: Path, *, name=None):
        root = Path(folder).resolve()
        root.mkdir(parents=True, exist_ok=True)
        if any(root.iterdir()):
            raise ProjectError("Create a project in an empty folder")
        lock = ProjectLock(root)
        store = cls(root, lock)
        store._project_id = str(uuid4())
        try:
            with closing(sqlite3.connect(store.path)) as connection, connection:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute(
                    "CREATE TABLE metadata(name TEXT NOT NULL, revision INTEGER NOT NULL, "
                    "project_id TEXT NOT NULL UNIQUE)"
                )
                connection.execute(
                    "INSERT INTO metadata VALUES(?, 0, ?)", (name or root.name, store._project_id)
                )
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
                    "payload_version INTEGER NOT NULL, wallet TEXT NOT NULL)"
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
                    CREATE TABLE project_economy(
                      id INTEGER PRIMARY KEY CHECK(id=1), payload_version INTEGER NOT NULL,
                      state TEXT NOT NULL);
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
                connection.execute(
                    "INSERT INTO project_economy VALUES(1,?,?)",
                    (ECONOMY_VERSION, encode_economy(CurrencySystem())),
                )
                connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            (root / "assets").mkdir()
            store._file_identity = cls._database_identity(store.path)
            store._stored = StoredRevision(ProjectSnapshot((), 0), {}, {})
        except sqlite3.Error as error:
            store.close()
            raise ProjectError(f"Cannot create project: {error}") from error
        except Exception:
            store.close()
            raise
        return store

    @classmethod
    def create_new(cls, folder: Path, snapshot=None):
        destination = folder.parent.resolve() / folder.name
        if destination.exists() or destination.is_symlink():
            raise ProjectError("Папка проекта уже существует. Выберите другое название.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".lodandsy-create-", dir=destination.parent
        ) as temporary:
            staging = Path(temporary)
            with closing(cls.create(staging, name=destination.name)) as store:
                if snapshot is not None:
                    store.save(snapshot)
                store.load()
            _publish_project(staging, destination)
        return cls.open(destination)

    @staticmethod
    def _check_schema(connection):
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise IncompatibleProjectError(version)
        return version

    @staticmethod
    def _database_identity(database):
        try:
            info = database.lstat()
        except FileNotFoundError as error:
            raise ProjectError(f"Нет файла мира {DATABASE_NAME} в выбранной папке.") from error
        if not stat.S_ISREG(info.st_mode) or database.resolve() != database:
            raise ProjectError("Файл базы должен находиться непосредственно в папке мира.")
        return info.st_dev, info.st_ino

    @classmethod
    def _read_metadata(cls, database):
        identity = cls._database_identity(database)
        try:
            with closing(connect_database(database, readonly=True)) as connection:
                connection.execute("PRAGMA busy_timeout=250")
                connection.execute("BEGIN")
                version = cls._check_schema(connection)
                rows = connection.execute("SELECT project_id FROM metadata LIMIT 2").fetchall()
                if len(rows) != 1:
                    raise ProjectError("В базе должна быть одна запись метаданных проекта.")
                project_id = rows[0][0]
                validate_id(project_id)
        except sqlite3.Error as error:
            raise ProjectError(
                f"Не удалось прочитать версию или метаданные проекта: {error}"
            ) from error
        except ValueError as error:
            if isinstance(error, ProjectError):
                raise
            raise ProjectError("Некорректный идентификатор проекта.") from error
        if cls._database_identity(database) != identity:
            raise ProjectError("Файл базы проекта был заменён во время чтения метаданных.")
        return ProjectMetadata(project_id, version, identity)

    @classmethod
    def inspect(cls, folder: Path):
        """Read catalogue metadata without decoding the world or taking its writer lease."""
        return cls._read_metadata(Path(folder).resolve() / DATABASE_NAME)

    @classmethod
    def open(cls, folder: Path):
        store, _ = cls.open_with_snapshot(folder)
        return store

    @classmethod
    def open_with_snapshot(cls, folder: Path, *, expected=None):
        root = Path(folder).resolve()
        database = root / DATABASE_NAME
        metadata = cls._read_metadata(database)
        if expected is not None and metadata != expected:
            raise ProjectError("Выбранный проект был заменён. Откройте каталог заново.")
        store = cls(root, ProjectLock(root))
        try:
            if cls._database_identity(database) != metadata.database_identity:
                raise ProjectError("Файл базы проекта был заменён до открытия.")
            store._project_id = metadata.project_id
            verified = store._load_verified()
            if cls._database_identity(database) != metadata.database_identity:
                raise ProjectError("Файл базы проекта был заменён во время проверки.")
            store._file_identity = metadata.database_identity
            store._stored = StoredRevision.verified(
                verified.snapshot, verified.map_versions, verified.entities,
            )
        except Exception:
            store.close()
            raise
        return store, verified

    def _check_open(self):
        if self._closed:
            raise ProjectError("Project has been closed")

    @property
    def project_id(self):
        self._check_open()
        if self._project_id is None:
            self.load()
        return self._project_id

    def load(self) -> ProjectSnapshot:
        return self._load_verified().snapshot

    @project_operation
    def _load_verified(self):
        verified, self._project_id = self._read_snapshot(self.path, self._project_id)
        return verified

    @classmethod
    def _read_snapshot(cls, path, expected_project_id=None):
        try:
            with closing(connect_database(path, readonly=True)) as connection:
                connection.execute("BEGIN")
                snapshot, versions, project_id = cls._decode_snapshot(
                    connection, expected_project_id,
                )
                collection = snapshot.entity_collection()
                snapshot = replace(
                    snapshot, cards=CardCollection(entities=collection).all(),
                    entities=collection.summaries(),
                )
                return VerifiedProject(snapshot, collection, versions), project_id
        except sqlite3.Error as error:
            raise ProjectError(f"Cannot read project: {error}") from error
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            if isinstance(error, ProjectError):
                raise
            raise ProjectError(f"Cannot read project: {error}") from error

    @classmethod
    def _decode_snapshot(cls, connection, expected_project_id):
        try:
            cls._check_schema(connection)
            if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ProjectError("Project database is damaged; restore a backup")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ProjectError("Project hierarchy contains missing parents")
            metadata = connection.execute("SELECT revision,project_id FROM metadata").fetchall()
            if len(metadata) != 1 or type(metadata[0][0]) is not int or metadata[0][0] < 0:
                raise ProjectError("Invalid project metadata")
            project_id = metadata[0][1]
            validate_id(project_id)
            if expected_project_id is not None and expected_project_id != project_id:
                raise ProjectError("Project identity changed")
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
            economy_rows = connection.execute(
                "SELECT payload_version,state FROM project_economy"
            ).fetchall()
            if len(economy_rows) != 1:
                raise ProjectError("Некорректные настройки экономики")
            currency, categories = decode_economy(*economy_rows[0])
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
            maps, tables = cls._load_modules(connection)
            cls._validate_modules(cards, assets, maps, tables)
            expected = {
                "card": "card_content",
                "map": "map_document",
                "table": "table_document",
            }
            for kind, table in expected.items():
                ids = {row[0] for row in connection.execute(f"SELECT id FROM {table}")}
                if ids != {e.id for e in envelopes if e.kind == kind}:
                    raise ProjectError("Entity payload inventory mismatch")
            snapshot = ProjectSnapshot(
                cards,
                metadata[0][0],
                assets,
                maps,
                tables,
                envelopes,
                rules,
                currency,
                categories,
            )
            versions = dict(connection.execute("SELECT id,payload_version FROM map_document"))
            return snapshot, versions, project_id
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
            versions = dict(connection.execute("SELECT id,payload_version FROM map_document"))
            if any(v not in (7, 8, 9, TRANSFORM_MAP_VERSION) for v in versions.values()):
                raise ValueError("Unsupported Map version")
            token_rows = {}
            for key, map_id, ordinal, card_id, actor_id, placement in connection.execute(
                "SELECT id,map_id,ordinal,card_id,actor_id,placement FROM map_token "
                "ORDER BY map_id,ordinal"
            ):
                entries = token_rows.setdefault(map_id, [])
                if ordinal != len(entries):
                    raise ValueError("Non-contiguous token order")
                values = json.loads(placement)
                extended = versions[map_id] == TRANSFORM_MAP_VERSION
                fields = TOKEN_FIELDS | {"rotation"} if extended else TOKEN_FIELDS
                if not isinstance(values, dict) or values.keys() != fields:
                    raise ValueError("Invalid Token placement fields")
                token = TokenInstance(card_id, id=key, actor_id=actor_id, **values)
                if not extended and token.uses_object_transform:
                    raise ValueError("Дробный размер и поворот требуют Map10")
                entries.append(token)
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
            for key, title, version, wallet in connection.execute(
                "SELECT t.id,e.title,t.payload_version,t.wallet FROM table_document t "
                "JOIN entity e ON e.id=t.id ORDER BY e.position,e.id"
            ):
                SQLiteProjectStore._require_version(version, 4, "Table")
                tables.append(
                    TableDocument(
                        title, key, tuple(columns.get(key, ())), tuple(rows.get(key, ())),
                        decode_wallet(wallet),
                    )
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
    def save(self, snapshot: ProjectSnapshot, expected_revision=None, *, _rewrite_all=False):
        if type(snapshot.revision) is not int or snapshot.revision < 0:
            raise ProjectError("Invalid snapshot revision")
        if expected_revision is not None and (
            type(expected_revision) is not int or expected_revision < 0
        ):
            raise ProjectError("Invalid acknowledged revision")
        collection = snapshot.entity_collection()
        snapshot = replace(
            snapshot, cards=CardCollection(entities=collection).all(),
            entities=collection.summaries(),
        )
        if len({asset.id for asset in snapshot.assets}) != len(snapshot.assets):
            raise ProjectError("Duplicate asset ID")
        self._validate_modules(snapshot.cards, snapshot.assets, snapshot.maps, snapshot.tables)
        self._check_identity()
        with closing(connect_database(self.path)) as connection, connection:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            persisted, map_versions, _ = self._decode_snapshot(connection, self.project_id)
            self._check_identity()
            recovered = self._confirm_stored_revision(persisted, map_versions)
            previous = self._stored
            current = persisted.revision
            retry = expected_revision is not None and expected_revision != current
            if retry and expected_revision != self._stored.acknowledged_base:
                raise ProjectError("Acknowledged revision does not match the saved project")
            if snapshot.revision <= current:
                if (recovered or retry) and previous.matches(snapshot, map_versions):
                    return
                raise ProjectError("Stale revision cannot overwrite the saved project")

            removed, changed = _entity_delta(previous, collection, _rewrite_all)
            versions = {
                document.id: _map_write_version(
                    document, previous.map_versions.get(document.id),
                    document.id in changed["map"],
                )
                for document in snapshot.maps
            }
            old_versions = previous.map_versions
            first_extended = current > 0 and TRANSFORM_MAP_VERSION not in old_versions.values()
            upgrading = any(
                version == TRANSFORM_MAP_VERSION
                and (first_extended or old_versions.get(key, version) < version)
                for key, version in versions.items()
            )
            if upgrading:
                self._backup_before_map_upgrade(previous)

            prior_assets = {asset.id: asset for asset in previous.snapshot.assets}
            for asset in snapshot.assets:
                if prior_assets.get(asset.id) != asset:
                    self._verify_asset(asset)

            self._write_delta(
                connection, previous, snapshot, removed, changed, versions, _rewrite_all,
            )
            if upgrading:
                written, _ = self._load_modules(connection)
                if (
                    {document.id: document for document in written}
                    != {document.id: document for document in snapshot.maps}
                    or connection.execute("PRAGMA quick_check").fetchone() != ("ok",)
                    or connection.execute("PRAGMA foreign_key_check").fetchone() is not None
                ):
                    raise ProjectError("Проверка перехода на Map10 не пройдена")
            updated = connection.execute(
                "UPDATE metadata SET revision=? WHERE project_id=? AND revision=?",
                (snapshot.revision, self.project_id, current),
            )
            if updated.rowcount != 1:
                raise ProjectError("Project revision changed during save")
            self._check_identity()
            self._pending = StoredRevision.verified(
                snapshot, versions, collection,
                acknowledged_base=current if expected_revision is None else expected_revision,
            )
            connection.commit()
            self._stored, self._pending = self._pending, None

    def _check_identity(self):
        if self._database_identity(self.path) != self._file_identity:
            raise ProjectError("Файл базы проекта был заменён. Откройте проект заново.")

    def _confirm_stored_revision(self, snapshot, map_versions):
        # Matching every typed value reuses the domain proof of a verified revision.
        # A different source must never be adopted as the base of a pending write.
        if self._stored.matches(snapshot, map_versions):
            self._pending = None
            return False
        if self._pending is not None and self._pending.matches(
            snapshot, map_versions,
        ):
            self._stored, self._pending = self._pending, None
            return True
        raise ProjectError("Сохранённые данные или ревизия проекта изменились вне писателя.")

    @staticmethod
    def _write_delta(connection, previous, target, removed, changed, versions, rewrite_all):
        before_assets = {asset.id: asset for asset in previous.snapshot.assets}
        after_assets = {asset.id: asset for asset in target.assets}
        for key, asset in before_assets.items():
            if rewrite_all or after_assets.get(key) != asset:
                connection.execute("DELETE FROM asset WHERE id=?", (key,))
        connection.executemany(
            "INSERT INTO asset VALUES(?,?,?,?)",
            (
                (a.id, a.path, a.sha256, a.size) for a in target.assets
                if rewrite_all or before_assets.get(a.id) != a
            ),
        )

        # Clear owned rows before inserting any replacements. A compound edit can move
        # a UUID or an inventory between aggregates that have SQL uniqueness constraints.
        old_kinds = {e.id: e.kind for e in previous.snapshot.entities}
        for kind, owner, tables in (
            ("card", "card_id", ("card_default_actor", "card_actor")),
            ("map", "map_id", ("map_token",)),
            ("table", "table_id", ("table_cell", "table_row", "table_column")),
        ):
            keys = removed[kind] | {key for key in changed[kind] if old_kinds.get(key) == kind}
            for table in tables:
                connection.executemany(
                    f"DELETE FROM {table} WHERE {owner}=?", ((key,) for key in keys),
                )
        for kind, table in (
            ("card", "card_content"), ("map", "map_document"), ("table", "table_document"),
        ):
            connection.executemany(
                f"DELETE FROM {table} WHERE id=?", ((key,) for key in removed[kind]),
            )
        after_ids = {entity.id for entity in target.entities}
        connection.executemany(
            "DELETE FROM entity WHERE id=?",
            (
                (entity.id,) for entity in previous.snapshot.entities
                if rewrite_all or entity.id not in after_ids
            ),
        )
        before = {entity.id: entity for entity in previous.snapshot.entities}
        connection.executemany(
            "INSERT INTO entity VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "kind=excluded.kind,title=excluded.title,parent_id=excluded.parent_id,"
            "position=excluded.position",
            (
                (e.id, e.kind, e.title, e.parent_id, e.position) for e in target.entities
                if rewrite_all or before.get(e.id) != e
            ),
        )

        _write_cards(connection, (c for c in target.cards if c.id in changed["card"]))
        _write_maps(connection, (m for m in target.maps if m.id in changed["map"]), versions)
        _write_tables(connection, (t for t in target.tables if t.id in changed["table"]))
        if rewrite_all or (target.currency, target.custom_categories) != (
            previous.snapshot.currency, previous.snapshot.custom_categories,
        ):
            connection.execute(
                "UPDATE project_economy SET state=? WHERE id=1",
                (encode_economy(target.currency, target.custom_categories),),
            )
        if rewrite_all or target.rules != previous.snapshot.rules:
            connection.execute(
                "UPDATE project_rules SET ruleset=?,rules_version=?,revision=?,overrides=? "
                "WHERE id=1",
                (
                    target.rules.ruleset, target.rules.version, target.rules.revision,
                    json.dumps(target.rules.overrides, ensure_ascii=False),
                ),
            )

    def _backup_before_map_upgrade(self, previous):
        archive = self.root.parent / f"LODANDSY-before-Map10-{uuid4().hex[:12]}.lodbackup"
        temporary_root = Path(tempfile.gettempdir()).resolve()
        size = self.backup(archive, verification_root=temporary_root)
        with ExitStack() as staging:
            with _disk_stage(temporary_root, VERIFY_STAGE, size):
                temporary = staging.enter_context(tempfile.TemporaryDirectory(
                    prefix="lodandsy-verify-map10-", dir=temporary_root,
                ))
            target = Path(temporary) / "world"
            restored, verified = self.restore_with_snapshot(archive, target, verification=True)
            with closing(restored):
                if restored.project_id != self.project_id or not previous.matches(
                    verified.snapshot, verified.map_versions,
                ):
                    raise ProjectError("Не прошла проверка резервной копии перед Map10")

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

    def _unregistered_assets(self, assets):
        registered = {asset.path for asset in assets}
        folder = self.root / "assets"
        resolved = folder.resolve()
        if not resolved.is_relative_to(self.root):
            raise ProjectError("Asset directory is outside the project")
        # Documents can refer to files that are absent from the SQL inventory.
        for path in sorted(folder.rglob("*")):
            name = path.relative_to(self.root).as_posix()
            if name not in registered and path.is_file():
                if not path.resolve().is_relative_to(resolved):
                    raise ProjectError("Asset path is outside the project")
                yield path, name, path.stat().st_size

    def _write_backup_archive(self, destination, database, assets):
        archive = destination.with_name(destination.name + f".{uuid4().hex}.tmp")
        try:
            with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
                bundle.write(database, DATABASE_NAME)
                for asset in assets:
                    self._verify_asset(asset)
                    info = zipfile.ZipInfo(asset.path)
                    info.file_size = asset.size
                    info.compress_type = bundle.compression
                    checksum, size = hashlib.sha256(), 0
                    with (self.root / asset.path).open("rb") as source:
                        with bundle.open(info, "w") as output:
                            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                                size += len(chunk)
                                if size > asset.size:
                                    raise ProjectError("Asset changed while creating backup")
                                output.write(chunk)
                                checksum.update(chunk)
                    if checksum.hexdigest() != asset.sha256 or size != asset.size:
                        raise ProjectError("Asset changed while creating backup")
                total = database.stat().st_size + sum(asset.size for asset in assets)
                for path, name, size in self._unregistered_assets(assets):
                    total += size
                    if total > MAX_BACKUP_BYTES:
                        raise ProjectError("Backup exceeds the supported 4 GiB restore budget")
                    bundle.write(path, name)
                total = sum(entry.file_size for entry in bundle.infolist())
                if total > MAX_BACKUP_BYTES:
                    raise ProjectError("Backup grew beyond the supported 4 GiB restore budget")
            with archive.open("r+b") as stream:
                os.fsync(stream.fileno())
            os.replace(archive, destination)
            return total
        finally:
            archive.unlink(missing_ok=True)

    @project_operation
    def backup(self, destination: Path, *, verification_root=None) -> int:
        destination = Path(destination).resolve()
        if destination.is_relative_to(self.root):
            raise ProjectError("Save backups outside the project folder")
        temporary_root = Path(tempfile.gettempdir()).resolve()
        with closing(connect_database(self.path, readonly=True)) as source:
            source.execute("BEGIN")
            page_size = source.execute("PRAGMA page_size").fetchone()[0]
            database_size = page_size * source.execute("PRAGMA page_count").fetchone()[0]
            assets = tuple(
                AssetRecord(*row) for row in source.execute("SELECT id,path,sha256,size FROM asset")
            )
            entries = [(DATABASE_NAME, database_size)]
            entries.extend((asset.path, asset.size) for asset in assets)
            entries.extend((name, size) for _, name, size in self._unregistered_assets(assets))
            total = sum(size for _, size in entries)
            if total > MAX_BACKUP_BYTES:
                raise ProjectError("Backup exceeds the supported 4 GiB restore budget")
            sqlite_bytes = database_size + page_size
            archive_bytes = _archive_requirement(entries)
            _preflight_backup(
                temporary_root, destination.parent, sqlite_bytes, archive_bytes,
                total, verification_root,
            )
            with ExitStack() as staging:
                with _disk_stage(temporary_root, TEMP_DB_STAGE, sqlite_bytes):
                    temporary = staging.enter_context(tempfile.TemporaryDirectory(
                        prefix="lodandsy-backup-", dir=temporary_root,
                    ))
                    database = Path(temporary) / DATABASE_NAME
                    with closing(sqlite3.connect(database)) as backup:
                        backup.execute("PRAGMA foreign_keys=ON")
                        source.backup(backup)
                with _disk_stage(destination, ARCHIVE_STAGE, archive_bytes):
                    return self._write_backup_archive(destination, database, assets)

    @classmethod
    def restore(cls, archive: Path, destination: Path, *, verification=False):
        store, _ = cls.restore_with_snapshot(archive, destination, verification=verification)
        return store

    @classmethod
    def restore_with_snapshot(cls, archive: Path, destination: Path, *, verification=False):
        destination = Path(destination)
        destination = destination.parent.resolve() / destination.name
        if destination.exists() or destination.is_symlink():
            raise ProjectError("Restore requires a new folder; existing data is never overwritten")
        stage = VERIFY_STAGE if verification else RESTORE_STAGE
        with zipfile.ZipFile(archive) as bundle:
            entries = bundle.infolist()
            names = [entry.filename for entry in entries]
            if len(set(names)) != len(names) or DATABASE_NAME not in names:
                raise ProjectError("Invalid backup inventory")
            total_size = sum(entry.file_size for entry in entries)
            if total_size > MAX_BACKUP_BYTES:
                raise ProjectError("Backup exceeds the 4 GiB restore limit")
            with _disk_stage(destination, stage, total_size):
                destination.parent.mkdir(parents=True, exist_ok=True)
                _require_space(destination.parent, stage, total_size)
                with tempfile.TemporaryDirectory(
                    prefix=".lodandsy-restore-", dir=destination.parent
                ) as temp:
                    staging = Path(temp).resolve()
                    assert staging.parent == destination.parent
                    cls._extract_verified_backup(bundle, entries, staging)
                    _publish_project(staging, destination)
        return cls.open_with_snapshot(destination)

    @classmethod
    def _extract_verified_backup(cls, bundle, entries, staging):
        for entry in entries:
            parts = PurePosixPath(entry.filename).parts
            allowed = entry.filename == DATABASE_NAME or (len(parts) >= 2 and parts[0] == "assets")
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
        validation, verified = cls.open_with_snapshot(staging)
        with closing(validation):
            for asset in verified.snapshot.assets:
                validation._verify_asset(asset)

    def close(self):
        with self._operation_lock:
            if not self._closed:
                self._closed = True
                self._lock.close()
