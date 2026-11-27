"""User-local opening history, independent from discovery on disk."""

import json
import os
from pathlib import Path

from PySide6.QtCore import QDateTime, QSettings, Qt


class ProjectHistory:
    def __init__(self, settings=None):
        self.settings = settings if settings is not None else QSettings("LODANDSY", "LODANDSY")

    @staticmethod
    def path(value):
        return str(Path(value).resolve())

    @staticmethod
    def identity(value):
        return os.path.normcase(os.path.normpath(value)).casefold()

    @property
    def entries(self):
        try:
            data = json.loads(self.settings.value("projects/catalogue", "[]"))
        except ValueError, TypeError:
            return ()
        if not isinstance(data, list):
            return ()
        return tuple(
            row
            for row in data
            if isinstance(row, dict)
            and {"path", "title"} <= row.keys() <= {"path", "title", "opened_at"}
            and all(isinstance(value, str) and value for value in row.values())
        )

    @property
    def last_directory(self):
        return self.settings.value("projects/lastDirectory", "")

    def remember(self, folder):
        path = self.path(folder)
        identity = self.identity(path)
        entries = [{
            "path": path, "title": Path(path).name or path,
            "opened_at": QDateTime.currentDateTimeUtc().toString(Qt.DateFormat.ISODate),
        }]
        entries.extend(e for e in self.entries if self.identity(e["path"]) != identity)
        self.settings.setValue("projects/catalogue", json.dumps(entries, ensure_ascii=False))
        self.settings.setValue("projects/lastDirectory", str(Path(path).parent))
        self.settings.sync()
