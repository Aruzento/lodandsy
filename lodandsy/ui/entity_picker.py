"""Virtualized native reference picker; catalog data is supplied through a public query API."""

from html import escape

from PySide6.QtCore import QAbstractListModel, QEvent, QModelIndex, Qt
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListView, QVBoxLayout

from lodandsy.ui.icons import icon, tree_card_icon


class ReferenceListModel(QAbstractListModel):
    def __init__(self, queries, kind=None, card_type=None, parent=None, *, predicate=None):
        super().__init__(parent)
        self.queries, self.kind, self.card_type = queries, kind, card_type
        self.ids = ()
        self.text = ""
        self.predicate = predicate
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
        if role == Qt.ItemDataRole.DecorationRole:
            return tree_card_icon(info.card_type) if info.kind == "card" else icon(info.kind)
        if role == Qt.ItemDataRole.DisplayRole:
            parent = info.path.rsplit(" / ", 1)[0] if " / " in info.path else "Корень проекта"
            return info.title + "\n" + parent + " · " + info.id[:8]
        if role == Qt.ItemDataRole.ToolTipRole:
            return escape(info.path + "\n" + info.id)

    def filter(self, text=None):
        if text is not None:
            self.text = text
        ids = self.queries.search(self.text, kind=self.kind, card_type=self.card_type)
        if self.predicate is not None:
            ids = tuple(key for key in ids if self.predicate(key))
        if ids != self.ids:
            self.beginResetModel()
            self.ids = ids
            self.endResetModel()

    def _changed(self, keys, fields):
        if fields & {
            "title",
            "aliases",
            "card_type",
            "created",
            "deleted",
            "parent_id",
            "position",
        }:
            self.filter()
        positions = {key: i for i, key in enumerate(self.ids)}
        for key in keys:
            if key in positions:
                index = self.index(positions[key])
                self.dataChanged.emit(index, index)


class EntityPicker(QDialog):
    def __init__(
        self, queries, column=None, parent=None, current=None, *, predicate=None, click=False,
    ):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("entityPicker")
        kind = getattr(column, "ref_kind", None)
        card_type = getattr(column, "ref_card_type", None)
        self.setWindowTitle("Выбрать предмет" if card_type == "item" else "Выбрать документ")
        self.resize(380, 320)
        self.chosen_id = None
        self.query = QLineEdit()
        self.query.setPlaceholderText("Название или другое имя…")
        self.query.setAccessibleName(
            "Поиск предмета" if card_type == "item" else "Поиск документа"
        )
        self.list = QListView()
        self.list.setAccessibleName("Результаты поиска документов")
        self.model = ReferenceListModel(queries, kind, card_type, self, predicate=predicate)
        self.list.setModel(self.model)
        self._selection_id = current
        self.model.modelAboutToBeReset.connect(self._remember_selection)
        self.model.modelReset.connect(lambda: self._select(self._selection_id))
        self.notice = QLabel()
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self.query)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.notice)
        self.query.textChanged.connect(self._search)
        self.query.returnPressed.connect(self._accept_current)
        self.list.activated.connect(lambda index: self._accept_current())
        if click:
            self.list.clicked.connect(lambda index: self._accept_current())
        self.query.installEventFilter(self)
        self._select(current)
        self.query.setFocus()

    def _select(self, key=None):
        position = self.model.ids.index(key) if key in self.model.ids else 0
        if self.model.ids:
            self.list.setCurrentIndex(self.model.index(position))
        self.notice.setText(
            "Нет подходящих документов"
            if not self.model.ids
            else f"Найдено: {len(self.model.ids)} · Enter — выбрать, Escape — отмена"
        )

    def _search(self, text):
        current = self.list.currentIndex().data(Qt.ItemDataRole.UserRole)
        self.model.filter(text)
        self._select(current)

    def _remember_selection(self):
        self._selection_id = self.list.currentIndex().data(Qt.ItemDataRole.UserRole)

    def _accept_current(self):
        key = self.list.currentIndex().data(Qt.ItemDataRole.UserRole)
        if key is not None:
            self.chosen_id = key
            self.accept()

    def eventFilter(self, obj, event):
        if (
            obj is self.query
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Down
        ):
            self.list.setFocus()
            if not self.list.currentIndex().isValid() and self.model.ids:
                self.list.setCurrentIndex(self.model.index(0))
            return True
        return super().eventFilter(obj, event)
