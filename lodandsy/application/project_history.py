"""User-local project catalogue; never part of a world or its backup."""

import json
import os
from pathlib import Path

from PySide6.QtCore import QSettings


class ProjectHistory:
    def __init__(self, settings=None):
        self.settings = settings if settings is not None else QSettings("LODANDSY", "LODANDSY")

    @staticmethod
    def path(value):
        return str(Path(value).resolve())

    @staticmethod
    def identity(value):
        return os.path.normcase(ProjectHistory.path(value)).casefold()

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
            and set(row) == {"path", "title"}
            and all(isinstance(value, str) and value for value in row.values())
        )

    @property
    def last_directory(self):
        return self.settings.value("projects/lastDirectory", "")

    def remember(self, folder, *, replaces=None):
        path = self.path(folder)
        identities = {self.identity(path)}
        if replaces:
            identities.add(self.identity(replaces))
        entries = [{"path": path, "title": Path(path).name or path}]
        entries.extend(e for e in self.entries if self.identity(e["path"]) not in identities)
        self.settings.setValue("projects/catalogue", json.dumps(entries, ensure_ascii=False))
        self.settings.setValue("projects/lastDirectory", str(Path(path).parent))
        self.settings.sync()

    def remove(self, folder):
        entries = [e for e in self.entries if self.identity(e["path"]) != self.identity(folder)]
        self.settings.setValue("projects/catalogue", json.dumps(entries, ensure_ascii=False))
        self.settings.sync()
