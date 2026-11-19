from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QStandardItem

from lodandsy.ui.card_tree_model import CARD_ID_ROLE, CardTreeModel

NODE_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 1
NODE_ID_ROLE = int(Qt.ItemDataRole.UserRole) + 2
NODE_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 3


class ProjectTreeModel(CardTreeModel):
    """Navigation summaries only; Card hierarchy stays in CardCollection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes = {}
        self._sections = {}
        for kind, title in [("card", "Карточки"), ("map", "Карты"), ("table", "Таблицы")]:
            item = self._node("section", kind, title)
            self._sections[kind] = item
            self.appendRow(item)
        self.appendRow(self._node("dice", "dice", "Кубики"))

    def _node(self, kind, entity_id, title):
        item = QStandardItem(title)
        item.setEditable(False)
        item.setData(kind, NODE_KIND_ROLE)
        item.setData(entity_id, NODE_ID_ROLE)
        key = f"{kind}:{entity_id}"
        item.setData(key, NODE_KEY_ROLE)
        if kind == "card":
            item.setData(entity_id, CARD_ID_ROLE)
        self._nodes[key] = item
        return item

    def index_for_node(self, key):
        item = self._nodes.get(key)
        return item.index() if item is not None else QModelIndex()

    def node_keys(self):
        return tuple(self._nodes)

    def section_index(self, kind):
        return self._sections[kind].index()

    def set_cards(self, cards):
        cards = tuple(cards)
        ids = {card.id for card in cards}
        if len(ids) != len(cards):
            raise ValueError("Card ids must be unique")
        for key in self._card_ids:
            self._nodes.pop(f"card:{key}", None)
        root = self._sections["card"]
        root.removeRows(0, root.rowCount())
        self._card_ids = ids
        self._items = {card.id: self._node("card", card.id, card.title) for card in cards}
        for card in cards:
            parent = self._items.get(card.parent_id, root)
            parent.appendRow(self._items[card.id])

    def set_module_entries(self, kind, entries):
        if kind not in {"map", "table"}:
            raise ValueError("Unsupported navigator kind")
        entries = tuple(entries)
        ids = {key for key, _title in entries}
        if len(ids) != len(entries):
            raise ValueError("Duplicate navigator ID")
        root = self._sections[kind]
        for row in reversed(range(root.rowCount())):
            item = root.child(row)
            if item.data(NODE_ID_ROLE) not in ids:
                self._nodes.pop(item.data(NODE_KEY_ROLE), None)
                root.removeRow(row)
        for key, title in entries:
            item = self._nodes.get(f"{kind}:{key}")
            if item is None:
                root.appendRow(self._node(kind, key, title))
            elif item.text() != title:
                item.setText(title)

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        kind, key = index.data(NODE_KIND_ROLE), index.data(NODE_ID_ROLE)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if kind == "card":
            flags |= Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled
        elif kind == "section" and key == "card":
            flags |= Qt.ItemFlag.ItemIsDropEnabled
        return flags

    def canDropMimeData(self, data, action, row, column, parent):
        if (action != Qt.DropAction.MoveAction or column not in {-1, 0}
                or not parent.isValid() or row < -1 or row > self.rowCount(parent)):
            return False
        kind, key = parent.data(NODE_KIND_ROLE), parent.data(NODE_ID_ROLE)
        if kind != "card" and (kind != "section" or key != "card"):
            return False
        card_id = self._card_id_from_mime(data)
        if card_id not in self._card_ids:
            return False
        current = parent
        while current.isValid():
            if current.data(CARD_ID_ROLE) == card_id:
                return False
            current = current.parent()
        return True

    def dropMimeData(self, data, action, row, column, parent):
        if action == Qt.DropAction.IgnoreAction:
            return True
        if not self.canDropMimeData(data, action, row, column, parent):
            return False
        card_id = self._card_id_from_mime(data)
        parent_id = parent.data(CARD_ID_ROLE)
        if row == -1:
            self.reparent_requested.emit(card_id, parent_id)
        else:
            source = self.index_for_card(card_id)
            if source.parent() == parent and source.row() < row:
                row -= 1
            self.move_requested.emit(card_id, parent_id, row)
        return True
