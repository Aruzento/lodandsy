from PySide6.QtCore import QByteArray, QMimeData, QModelIndex, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel

from lodandsy.ui.icons import icon, tree_card_icon

NODE_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 1
NODE_ID_ROLE = int(Qt.ItemDataRole.UserRole) + 2
NODE_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 3
ENTITY_MIME_TYPE = "application/x-lodandsy-entity-id"


class ProjectTreeModel(QStandardItemModel):
    """A projection of the canonical mixed forest; never owns document payloads."""

    reparent_requested = Signal(str, object)
    move_requested = Signal(str, object, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes, self._items = {}, {}
        self._icons = {kind: icon(kind) for kind in ("map", "table")}

    def index_for_node(self, key):
        item = self._nodes.get(key)
        return item.index() if item is not None else QModelIndex()

    def node_keys(self):
        return tuple(self._nodes)

    def set_title(self, key, title):
        self._items[key].setText(title)

    def _decoration(self, entity, card_types):
        if entity.kind == "card":
            return tree_card_icon(card_types.get(entity.id))
        return self._icons[entity.kind]

    def set_entities(self, entities, *, card_types=None):
        entities = tuple(entities)
        card_types = card_types or {}
        ids = {entity.id for entity in entities}
        if len(ids) != len(entities):
            raise ValueError("Entity ids must be unique")
        if any(e.parent_id is not None and e.parent_id not in ids for e in entities):
            raise ValueError("Unknown parent in entity summaries")
        if ids == set(self._items) and all(
            (
                self._items[e.id].data(NODE_KIND_ROLE) == e.kind
                and self._items[e.id].index().parent().data(NODE_ID_ROLE) == e.parent_id
                and self._items[e.id].row() == e.position
            )
            for e in entities
        ):
            for entity in entities:
                item = self._items[entity.id]
                if item.text() != entity.title:
                    item.setText(entity.title)
                decoration = self._decoration(entity, card_types)
                if item.icon().cacheKey() != decoration.cacheKey():
                    item.setIcon(decoration)
            return
        self.clear()
        self._nodes, self._items = {}, {}
        for entity in entities:
            item = QStandardItem(self._decoration(entity, card_types), entity.title)
            item.setEditable(False)
            item.setData(entity.kind, NODE_KIND_ROLE)
            item.setData(entity.id, NODE_ID_ROLE)
            item.setData(f"{entity.kind}:{entity.id}", NODE_KEY_ROLE)
            self._nodes[f"{entity.kind}:{entity.id}"] = item
            self._items[entity.id] = item
        for entity in entities:
            parent = self._items.get(entity.parent_id, self.invisibleRootItem())
            parent.appendRow(self._items[entity.id])

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )

    def mimeTypes(self):
        return [ENTITY_MIME_TYPE]

    def mimeData(self, indexes):
        data = QMimeData()
        for index in indexes:
            if index.isValid() and index.column() == 0:
                data.setData(ENTITY_MIME_TYPE, QByteArray(index.data(NODE_ID_ROLE).encode()))
                break
        return data

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def supportedDragActions(self):
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

    @staticmethod
    def _id_from_mime(data):
        if data.hasFormat(ENTITY_MIME_TYPE):
            try:
                return bytes(data.data(ENTITY_MIME_TYPE)).decode("utf-8")
            except UnicodeDecodeError:
                pass
        return None

    def canDropMimeData(self, data, action, row, column, parent):
        if (
            action != Qt.DropAction.MoveAction
            or column not in {-1, 0}
            or row < -1
            or row > self.rowCount(parent)
        ):
            return False
        key = self._id_from_mime(data)
        if key not in self._items:
            return False
        current = parent
        while current.isValid():
            if current.data(NODE_ID_ROLE) == key:
                return False
            current = current.parent()
        return True

    def dropMimeData(self, data, action, row, column, parent):
        if action == Qt.DropAction.IgnoreAction:
            return True
        if not self.canDropMimeData(data, action, row, column, parent):
            return False
        key = self._id_from_mime(data)
        parent_id = parent.data(NODE_ID_ROLE)
        if row == -1:
            self.reparent_requested.emit(key, parent_id)
        else:
            source = self._items[key].index()
            if source.parent() == parent and source.row() < row:
                row -= 1
            self.move_requested.emit(key, parent_id, row)
        return True
