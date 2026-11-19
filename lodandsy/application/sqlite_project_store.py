import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import zipfile
from contextlib import closing
from dataclasses import asdict, dataclass
from functools import wraps
from pathlib import Path, PurePosixPath
from uuid import uuid4

from lodandsy.domain.card import Card, validate_card_id
from lodandsy.domain.card_collection import CardCollection
from lodandsy.domain.map_document import MapDocument, MapGrid, MapPin, MapToken
from lodandsy.domain.tools import RandomTable

DATABASE_NAME = "project.sqlite3"
SCHEMA_VERSION = 4
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
        if (len(parts) != 2 or parts[0] != "assets" or "\\" in self.path
                or ":" in self.path or ".." in parts):
            raise ProjectError("Asset path must be relative to assets/")
        if (not isinstance(self.sha256, str) or len(self.sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.sha256)):
            raise ProjectError("Invalid asset checksum")
        if type(self.size) is not int or self.size < 0:
            raise ProjectError("Invalid asset size")


@dataclass(frozen=True)
class ProjectSnapshot:
    cards: tuple[Card, ...]
    revision: int
    assets: tuple[AssetRecord, ...] = ()
    maps: tuple[MapDocument, ...] = ()
    tables: tuple[RandomTable, ...] = ()


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
    connection = sqlite3.connect(path.as_uri() + ("?mode=ro" if readonly else "?mode=rw"),
                                 uri=True, timeout=5)
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
                    "DEFERRABLE INITIALLY DEFERRED, position INTEGER NOT NULL CHECK(position>=0), "
                    "payload_version INTEGER NOT NULL, content TEXT NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE asset(id TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, "
                    "sha256 TEXT NOT NULL, size INTEGER NOT NULL CHECK(size>=0))"
                )
                connection.execute(
                    "CREATE INDEX entity_parent_position ON entity(parent_id,position)"
                )
                cls._upgrade_v2(connection)
                cls._upgrade_v3(connection)
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
            if store._loaded_version < SCHEMA_VERSION:
                store._migrate()
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
                if version not in {1, 2, 3, SCHEMA_VERSION}:
                    raise ProjectError(f"Unsupported project schema version: {version}")
                self._loaded_version = version
                if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise ProjectError("Project database is damaged; restore a backup")
                if connection.execute("PRAGMA foreign_key_check").fetchall():
                    raise ProjectError("Project hierarchy contains missing parents")
                metadata = connection.execute("SELECT revision FROM metadata").fetchall()
                if len(metadata) != 1 or type(metadata[0][0]) is not int or metadata[0][0] < 0:
                    raise ProjectError("Invalid project metadata")
                rows = connection.execute(
                    "SELECT id,kind,title,parent_id,position,payload_version,content "
                    "FROM entity ORDER BY position,id"
                ).fetchall()
                cards, positions = [], {}
                for card_id, kind, title, parent_id, position, payload_version, content in rows:
                    if kind != "card" or payload_version != 1:
                        raise ProjectError(
                            f"Unsupported entity kind/version: {kind}/{payload_version}"
                        )
                    expected = positions.get(parent_id, 0)
                    if type(position) is not int or position != expected:
                        raise ProjectError("Invalid sibling positions")
                    positions[parent_id] = expected + 1
                    cards.append(Card(title, card_id, parent_id, content))
                ordered_cards = CardCollection(cards).all()
                assets = tuple(AssetRecord(*row) for row in connection.execute(
                    "SELECT id,path,sha256,size FROM asset ORDER BY id"
                ))
                maps, tables = (), ()
                if version >= 3:
                    maps, tables = self._load_modules(connection)
                self._validate_modules(ordered_cards, assets, maps, tables)
                return ProjectSnapshot(ordered_cards, metadata[0][0], assets, maps, tables)
        except sqlite3.Error as error:
            raise ProjectError(f"Cannot read project: {error}") from error

    @staticmethod
    def _upgrade_v1(connection):
        connection.execute("CREATE INDEX entity_parent_position ON entity(parent_id,position)")
        connection.execute("PRAGMA user_version=2")

    @staticmethod
    def _upgrade_v2(connection):
        connection.execute(
            "CREATE TABLE map_document(id TEXT PRIMARY KEY, title TEXT NOT NULL, "
            "asset_id TEXT NOT NULL REFERENCES asset(id), payload_version INTEGER NOT NULL, "
            "pins TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE random_table(id TEXT PRIMARY KEY, title TEXT NOT NULL, "
            "payload_version INTEGER NOT NULL, rows TEXT NOT NULL)"
        )
        connection.execute("PRAGMA user_version=3")

    @staticmethod
    def _upgrade_v3(connection):
        connection.execute("ALTER TABLE map_document ADD COLUMN tokens TEXT NOT NULL DEFAULT '[]'")
        connection.execute("ALTER TABLE map_document ADD COLUMN grid TEXT NOT NULL DEFAULT '{}'")
        connection.execute("UPDATE map_document SET payload_version=2")
        connection.execute("PRAGMA user_version=4")

    @staticmethod
    def _load_modules(connection):
        maps, tables = [], []
        try:
            schema = connection.execute("PRAGMA user_version").fetchone()[0]
            fields = ",tokens,grid" if schema >= 4 else ", '[]', '{}'"
            for key, title, asset, version, payload, tokens_payload, grid_payload in (
                connection.execute("SELECT id,title,asset_id,payload_version,pins" + fields
                                   + " FROM map_document ORDER BY rowid")
            ):
                if version != (2 if schema >= 4 else 1):
                    raise ProjectError(f"Unsupported Map payload version: {version}")
                pins = json.loads(payload)
                if not isinstance(pins, list):
                    raise ValueError("Invalid markers")
                tokens = json.loads(tokens_payload)
                grid = json.loads(grid_payload)
                if not isinstance(tokens, list) or not isinstance(grid, dict):
                    raise ValueError("Invalid tokens/grid")
                maps.append(MapDocument(title, asset, key, tuple(MapPin(**pin) for pin in pins),
                                        tuple(MapToken(**token) for token in tokens),
                                        MapGrid(**grid)))
            for key, title, version, payload in connection.execute(
                "SELECT id,title,payload_version,rows FROM random_table ORDER BY rowid"
            ):
                if version != 1:
                    raise ProjectError(f"Unsupported Tools payload version: {version}")
                rows = json.loads(payload)
                if not isinstance(rows, list):
                    raise ValueError("Invalid table rows")
                tables.append(RandomTable(title, key, tuple(rows)))
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

    def _migrate(self):
        # Migrations only change the DB; immutable assets are untouched.
        # Keep a consistent database backup before the first schema-changing statement.
        folder = self.root / "backups"
        folder.mkdir(exist_ok=True)
        if not folder.resolve().is_relative_to(self.root):
            raise ProjectError("Migration backup directory is outside the project")
        version = self._loaded_version
        backup_path = folder / f"schema-v{version}-{uuid4().hex}.sqlite3"
        with backup_path.open("xb"):
            pass
        with closing(connect_database(self.path, readonly=True)) as source:
            with closing(sqlite3.connect(backup_path)) as backup:
                backup.execute("PRAGMA foreign_keys=ON")
                source.backup(backup)
        try:
            with closing(connect_database(self.path)) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                if connection.execute("PRAGMA user_version").fetchone()[0] != version:
                    raise ProjectError("Schema changed before migration; refusing to continue")
                if version == 1:
                    self._upgrade_v1(connection)
                if version <= 2:
                    self._upgrade_v2(connection)
                self._upgrade_v3(connection)
        except sqlite3.Error as error:
            raise ProjectError(f"Migration failed; original schema retained: {error}") from error

    @project_operation
    def save(self, snapshot: ProjectSnapshot):
        self._check_open()
        cards = CardCollection(snapshot.cards).all()
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
            if connection.execute(
                "SELECT 1 FROM entity WHERE kind!='card' OR payload_version!=1 LIMIT 1"
            ).fetchone():
                raise ProjectError("Unsupported entity; save refused without changing data")
            current = connection.execute("SELECT revision FROM metadata").fetchone()[0]
            if snapshot.revision <= current:
                raise ProjectError("Stale revision cannot overwrite a newer project")
            # Validate existing module versions before replacing any canonical payload.
            self._load_modules(connection)
            existing_assets = {row[0]: AssetRecord(*row) for row in connection.execute(
                "SELECT id,path,sha256,size FROM asset"
            )}
            for asset in snapshot.assets:
                if existing_assets.get(asset.id) != asset:
                    self._verify_asset(asset)
            connection.execute("DELETE FROM entity")
            counts = {}
            records = []
            for card in cards:
                position = counts.get(card.parent_id, 0)
                counts[card.parent_id] = position + 1
                records.append(
                    (card.id, "card", card.title, card.parent_id, position, 1, card.content)
                )
            connection.executemany("INSERT INTO entity VALUES(?,?,?,?,?,?,?)", records)
            connection.execute("DELETE FROM map_document")
            connection.execute("DELETE FROM random_table")
            connection.execute("DELETE FROM asset")
            connection.executemany("INSERT INTO asset VALUES(?,?,?,?)", [
                (a.id, a.path, a.sha256, a.size) for a in snapshot.assets
            ])
            connection.executemany("INSERT INTO map_document VALUES(?,?,?,?,?,?,?)", [
                (m.id, m.title, m.asset_id, 2,
                 json.dumps([asdict(pin) for pin in m.pins], ensure_ascii=False),
                 json.dumps([asdict(token) for token in m.tokens], ensure_ascii=False),
                 json.dumps(asdict(m.grid)))
                for m in snapshot.maps
            ])
            connection.executemany("INSERT INTO random_table VALUES(?,?,?,?)", [
                (t.id, t.title, 1, json.dumps(t.rows, ensure_ascii=False)) for t in snapshot.tables
            ])
            connection.execute("UPDATE metadata SET revision=?", (snapshot.revision,))

    @project_operation
    def import_asset(self, source: Path, *, known_assets=(), max_bytes=None,
                     cancelled=lambda: False) -> AssetRecord:
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
                    except (OSError, ValueError):
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
                    assets = tuple(AssetRecord(*row) for row in backup.execute(
                        "SELECT id,path,sha256,size FROM asset"
                    ))
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
                    # Markdown may reference user-supplied files inside assets too.
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
                    if (not allowed or ".." in parts or "\\" in entry.filename
                            or ":" in entry.filename or entry.is_dir()
                            or (entry.external_attr >> 16) & 0o170000 == 0o120000):
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
