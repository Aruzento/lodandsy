"""ID-indexed public catalog for relation pickers and the Object Card library."""

from dataclasses import replace

from PySide6.QtCore import QObject, Signal

from lodandsy.domain.entity_reference import ReferenceInfo


class EntityQueries(QObject):
    changed = Signal(object, object)
    reset_done = Signal()

    def __init__(self, core, card_provider, parent=None, *, type_options=(), field_options=()):
        super().__init__(parent)
        self.core, self.card_provider = core, card_provider
        self.type_options, self.field_options = tuple(type_options), tuple(field_options)
        self._info = {}
        self._search = {}
        core.entity_created.connect(lambda key: self.refresh(key, frozenset({"created"})))
        core.entity_changed.connect(self._structure_changed)
        core.entities_deleted.connect(self._deleted)
        core.replaced.connect(self.reset)
        self.reset()

    def path(self, key):
        parts = []
        while key is not None:
            node = self.core.entities.get(key)
            parts.append(node.title)
            key = node.parent_id
        return " / ".join(reversed(parts))

    def _read(self, key):
        node = self.core.entities.get(key)
        info = (
            self.card_provider(key)
            if node.kind == "card"
            else ReferenceInfo(key, node.kind, node.title, fields=(("title", node.title),))
        )
        return replace(info, path=self.path(key))

    def reset(self):
        self._info.clear()
        self._search.clear()
        for entity in self.core.entities.summaries():
            self._cache(self._read(entity.id))
        self.reset_done.emit()

    def _cache(self, info):
        self._info[info.id] = info
        self._search[info.id] = " ".join((info.title, *info.aliases)).casefold()

    def info(self, key):
        return self._info.get(key)

    def resolve(self, key, kind=None, card_type=None):
        info = self._info.get(key)
        return (
            info
            if info
            and (kind is None or info.kind == kind)
            and (card_type is None or info.card_type == card_type)
            else None
        )

    def search(self, text="", *, kind=None, card_type=None, with_image=False):
        needle = text.strip().casefold()
        return tuple(
            sorted(
                (
                    key
                    for key, info in self._info.items()
                    if (kind is None or info.kind == kind)
                    and (card_type is None or info.card_type == card_type)
                    and (not with_image or info.image_id)
                    and (not needle or needle in self._search[key])
                ),
                key=lambda key: (
                    self._info[key].title.casefold(),
                    self._info[key].path.casefold(),
                    key,
                ),
            )
        )

    def refresh(self, key, fields):
        affected = {key}
        try:
            self._cache(self._read(key))
            if fields & {"title", "parent_id", "position"}:
                for child in self.core.entities.descendant_ids(key):
                    if child in self._info:
                        self._info[child] = replace(self._info[child], path=self.path(child))
                        affected.add(child)
        except ValueError:
            self._info.pop(key, None)
            self._search.pop(key, None)
        self.changed.emit(frozenset(affected), fields)

    def _structure_changed(self, key, fields):
        if self.core.entities.get(key).kind != "card":
            self.refresh(key, fields)

    def _deleted(self, keys):
        for key in keys:
            self._info.pop(key, None)
            self._search.pop(key, None)
        self.changed.emit(frozenset(keys), frozenset({"deleted"}))
