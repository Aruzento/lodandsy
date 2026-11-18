from collections.abc import Iterable

from PySide6.QtCore import (
    QByteArray,
    QMimeData,
    QModelIndex,
    QObject,
    Qt,
    Signal,
)
from PySide6.QtGui import QStandardItem, QStandardItemModel

from lodandsy.domain.card import Card
from lodandsy.domain.entity_summary import EntitySummary

CARD_ID_ROLE = Qt.ItemDataRole.UserRole
CARD_MIME_TYPE = "application/x-lodandsy-card-id"


class CardTreeModel(QStandardItemModel):
    reparent_requested = Signal(str, object)
    move_requested = Signal(str, object, int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._card_ids: set[str] = set()
        self._items: dict[str, QStandardItem] = {}

    def index_for_card(self, card_id: str) -> QModelIndex:
        item = self._items.get(card_id)
        return item.index() if item is not None else QModelIndex()

    def card_ids(self) -> tuple[str, ...]:
        return tuple(self._items)

    def set_title(self, card_id: str, title: str) -> None:
        self._items[card_id].setText(title)

    def set_cards(self, cards: Iterable[Card | EntitySummary]) -> None:
        card_list = list(cards)

        card_ids = {
            card.id
            for card in card_list
        }

        if len(card_ids) != len(card_list):
            raise ValueError("Card ids must be unique")

        self._card_ids = card_ids
        self.clear()

        items = {
            card.id: self._create_item(card)
            for card in card_list
        }
        self._items = items

        root = self.invisibleRootItem()

        for card in card_list:
            item = items[card.id]

            if card.parent_id is None:
                root.appendRow(item)
                continue

            parent_item = items.get(card.parent_id)

            if parent_item is None:
                root.appendRow(item)
                continue

            parent_item.appendRow(item)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled

        return (
            super().flags(index)
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )

    def mimeTypes(self) -> list[str]:
        return [CARD_MIME_TYPE]

    def mimeData(
        self,
        indexes: list[QModelIndex],
    ) -> QMimeData:
        mime_data = QMimeData()

        for index in indexes:
            if not index.isValid() or index.column() != 0:
                continue

            card_id = index.data(CARD_ID_ROLE)

            if not isinstance(card_id, str):
                continue

            mime_data.setData(
                CARD_MIME_TYPE,
                QByteArray(card_id.encode("utf-8")),
            )
            break

        return mime_data

    def supportedDragActions(self) -> Qt.DropAction:
        return Qt.DropAction.MoveAction

    def supportedDropActions(self) -> Qt.DropAction:
        return Qt.DropAction.MoveAction

    def canDropMimeData(
        self,
        data: QMimeData,
        action: Qt.DropAction,
        row: int,
        column: int,
        parent: QModelIndex,
    ) -> bool:
        if action != Qt.DropAction.MoveAction:
            return False

        card_id = self._card_id_from_mime(data)

        if card_id is None:
            return False

        if card_id not in self._card_ids:
            return False

        if column not in {-1, 0} or row < -1 or row > self.rowCount(parent):
            return False

        current = parent

        while current.isValid():
            current_id = current.data(CARD_ID_ROLE)

            if current_id == card_id:
                return False

            current = current.parent()

        if parent.isValid():
            parent_id = parent.data(CARD_ID_ROLE)

            if not isinstance(parent_id, str):
                return False

        return True

    def dropMimeData(
        self,
        data: QMimeData,
        action: Qt.DropAction,
        row: int,
        column: int,
        parent: QModelIndex,
    ) -> bool:
        if action == Qt.DropAction.IgnoreAction:
            return True

        if not self.canDropMimeData(
            data,
            action,
            row,
            column,
            parent,
        ):
            return False

        card_id = self._card_id_from_mime(data)

        if card_id is None:
            return False

        new_parent_id: str | None = None

        if parent.isValid():
            parent_id = parent.data(CARD_ID_ROLE)

            if not isinstance(parent_id, str):
                return False

            new_parent_id = parent_id

        if row < 0:
            self.reparent_requested.emit(card_id, new_parent_id)
        else:
            source = self.index_for_card(card_id)
            if source.parent() == parent and source.row() < row:
                row -= 1
            self.move_requested.emit(card_id, new_parent_id, row)

        return True

    @staticmethod
    def _card_id_from_mime(
        data: QMimeData,
    ) -> str | None:
        if not data.hasFormat(CARD_MIME_TYPE):
            return None

        raw_data = bytes(
            data.data(CARD_MIME_TYPE)
        )

        if not raw_data:
            return None

        try:
            card_id = raw_data.decode("utf-8")
        except UnicodeDecodeError:
            return None

        if not card_id:
            return None

        return card_id

    @staticmethod
    def _create_item(card: Card | EntitySummary) -> QStandardItem:
        item = QStandardItem(card.title)
        item.setEditable(False)
        item.setData(card.id, CARD_ID_ROLE)

        return item
