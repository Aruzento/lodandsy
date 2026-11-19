"""The selected project's resources; shared explicitly, never discovered via a controller."""

from PySide6.QtCore import QObject, Signal


class ProjectResources(QObject):
    asset_changed = Signal(str)

    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        self.store = None
        self.assets = {}
        self.root = None
        self.generation = 0

    def select_store(self, store):
        if store is not self.store:
            self.generation += 1
            self.store = store
            self.root = store.root if store is not None else None

    def asset(self, key):
        return self.assets.get(key)
