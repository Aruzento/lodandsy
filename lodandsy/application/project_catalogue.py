"""Discover and reserve direct children of the system Documents project directory."""

import ntpath
import stat
from contextlib import closing, contextmanager
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from lodandsy.application.sqlite_project_store import (
    DATABASE_NAME,
    LOCK_NAME,
    IncompatibleProjectError,
    ProjectError,
    ProjectLock,
    SQLiteProjectStore,
)

# Leave room for database sidecars and the longest workspace-recovery filename.
MAX_WORLD_PATH = 200
WINDOWS_PATH_CHARACTERS = '<>:"/\\|?*'


def _system_documents():
    return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)


def _ordinary_directory(path):
    return (
        stat.S_ISDIR(path.lstat().st_mode)
        and not path.is_junction()
        and path.resolve() == path
    )


class ProjectCatalogue:
    def __init__(self, documents=None):
        self._documents = documents if documents is not None else _system_documents

    @property
    def root(self):
        location = self._documents()
        if not location or not Path(location).is_absolute():
            raise ProjectError("Системная папка «Документы» недоступна.")
        return Path(location).resolve() / "LODANDSY" / "project"

    def _directory(self, *, create=False):
        root = self.root
        for path in (root.parent, root):
            if create:
                # The system Documents directory itself can be missing on a fresh profile.
                path.mkdir(parents=True, exist_ok=True)
            try:
                ordinary = _ordinary_directory(path)
            except FileNotFoundError:
                if not create:
                    return root
                raise
            if not ordinary:
                raise ProjectError(f"Управляемый каталог должен быть обычной папкой: {path}")
        return root

    def destination(self, name):
        if (
            not isinstance(name, str) or not name.strip() or name in {".", ".."}
            or any(char in WINDOWS_PATH_CHARACTERS or ord(char) < 32 for char in name)
            or ntpath.isreserved(name)
            or name.casefold().startswith(".lodandsy-")
        ):
            raise ProjectError("Введите допустимое название проекта для Windows.")
        root = self.root
        path = root / name
        if path.parent != root:
            raise ProjectError("Название проекта должно обозначать одну папку.")
        try:
            units = len(str(path).encode("utf-16-le")) // 2
        except UnicodeEncodeError as error:
            raise ProjectError("Название содержит некорректный символ Unicode.") from error
        if units > MAX_WORLD_PATH:
            raise ProjectError(f"Слишком длинный путь. Предел — {MAX_WORLD_PATH} единиц UTF-16.")
        return path

    @contextmanager
    def reserve(self, name):
        path = self.destination(name)
        root = self._directory(create=True)
        if path.parent != root:
            raise ProjectError("Системная папка «Документы» изменилась. Повторите операцию.")
        try:
            lease = ProjectLock(root, ".lodandsy-catalogue.lock")
        except ProjectError as error:
            raise ProjectError("Каталог проектов занят. Повторите операцию.") from error
        with closing(lease):
            if any(child.name.casefold() == path.name.casefold() for child in root.iterdir()):
                raise ProjectError("Папка проекта уже существует. Выберите другое название.")
            yield path

    def entries(self, history):
        root = self._directory()
        recent = {
            entry["path"].casefold(): (rank, entry.get("opened_at"))
            for rank, entry in enumerate(history)
        }
        entries = []
        try:
            children = sorted(root.iterdir(), key=lambda path: path.name.casefold())
        except FileNotFoundError:
            return ()
        for child in children:
            if child.name.startswith((".lodandsy-create-", ".lodandsy-restore-")):
                continue
            metadata, version = None, None
            try:
                if not _ordinary_directory(child):
                    continue
                if not ((child / DATABASE_NAME).exists() or (child / LOCK_NAME).exists()):
                    continue
                metadata = SQLiteProjectStore.inspect(child)
                version = metadata.schema_version
                status, error = "pending", ""
            except IncompatibleProjectError as issue:
                version = issue.version
                status, error = "incompatible", str(issue)
            except (OSError, ProjectError) as issue:
                status, error = "metadata_error", str(issue)
            rank, opened_at = recent.get(str(child).casefold(), (len(recent), None))
            entries.append((rank, {
                "path": str(child), "title": child.name, "error": error,
                "opened_at": opened_at, "status": status,
                "schema_version": version, "metadata": metadata,
            }))
        return tuple(entry for _, entry in sorted(entries, key=lambda item: item[0]))
