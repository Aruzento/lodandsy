"""Object Card catalog. Images are original assets; portrait crops never enter this view."""

from collections import OrderedDict
from html import escape

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt
from PySide6.QtGui import QIcon, QPixmap


class ObjectLibraryModel(QAbstractListModel):
    def __init__(self, queries, image_size, image_provider, parent=None):
        super().__init__(parent)
        self.queries, self.image_size, self.image_provider = queries, image_size, image_provider
        self.ids, self.text = (), ""
        self._icons = OrderedDict()
        queries.changed.connect(self._changed)
        queries.reset_done.connect(self.filter)
        self.filter()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.ids)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.ids):
            return None
        info = self.queries.info(self.ids[index.row()])
        if info is None:
            return None
        if role == Qt.ItemDataRole.UserRole:
            return info.id
        if role == Qt.ItemDataRole.DisplayRole:
            return info.title
        if role == Qt.ItemDataRole.ToolTipRole:
            return escape(info.path + "\n" + info.id)
        if role == Qt.ItemDataRole.DecorationRole:
            if info.image_id in self._icons:
                self._icons.move_to_end(info.image_id)
                return self._icons[info.image_id]
            image = self.image_provider(info.image_id)
            if image is not None and not image.isNull():
                value = QIcon(
                    QPixmap.fromImage(image).scaled(
                        48,
                        48,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self._icons[info.image_id] = value
                while len(self._icons) > 128:
                    self._icons.popitem(last=False)
                return value

    def filter(self, text=None):
        if text is not None:
            self.text = text
        ids = tuple(
            key
            for key in self.queries.search(
                self.text, kind="card", card_type="object", with_image=True
            )
            if self.image_size(self.queries.info(key).image_id) is not None
        )
        if self.ids != ids:
            self.beginResetModel()
            self.ids = ids
            self.endResetModel()

    def _changed(self, keys, fields):
        if fields & {
            "created",
            "deleted",
            "title",
            "aliases",
            "portrait",
            "card_type",
            "parent_id",
        }:
            self.filter()
            for key in keys:
                if key in self.ids:
                    index = self.index(self.ids.index(key))
                    self.dataChanged.emit(index, index)

    def images_changed(self):
        self.filter()
        if self.ids:
            self.dataChanged.emit(
                self.index(0), self.index(len(self.ids) - 1), [Qt.ItemDataRole.DecorationRole]
            )
