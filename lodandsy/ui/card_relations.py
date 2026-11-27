from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class CardRelations(QWidget):
    actor_requested = Signal(str)
    placement_requested = Signal(str, str)
    inventory_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setMaximumHeight(240)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Участник / размещение", "Состояние"])
        self.tree.itemDoubleClicked.connect(self.activate)
        self.rows = {}
        layout.addWidget(self.tree)
        buttons = QHBoxLayout()
        for label, callback in (
            ("Состояние", self.open_actor),
            ("Инвентарь", self.open_inventory),
            ("Удалить участника…", self.delete_actor),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.hide()

    def set_rows(self, rows):
        ids = {row[0] for row in rows}
        for key in self.rows.keys() - ids:
            item = self.rows.pop(key)
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
        for key, name, summary, inventory, placements in rows:
            item = self.rows.get(key)
            if item is None:
                item = QTreeWidgetItem(self.tree)
                self.rows[key] = item
            item.setText(0, name)
            item.setText(1, summary)
            item.setToolTip(0, key)
            item.setData(0, Qt.ItemDataRole.UserRole, ("actor", key, inventory))
            if placements is None:
                continue
            existing = {
                item.child(i).data(0, Qt.ItemDataRole.UserRole): item.child(i)
                for i in range(item.childCount())
            }
            wanted = set()
            for map_id, token_id, title in placements:
                data = ("placement", map_id, token_id)
                wanted.add(data)
                child = existing.get(data)
                if child is None:
                    child = QTreeWidgetItem(item)
                child.setText(0, title)
                child.setText(1, token_id[:8])
                child.setData(0, Qt.ItemDataRole.UserRole, data)
            for data, child in existing.items():
                if data not in wanted:
                    item.removeChild(child)

    def selected(self):
        item = self.tree.currentItem()
        if item is not None and item.parent() is not None:
            item = item.parent()
        return item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None

    def activate(self, item, column=0):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data[0] == "placement":
            self.placement_requested.emit(data[1], data[2])
        else:
            self.actor_requested.emit(data[1])

    def open_actor(self):
        data = self.selected()
        if data:
            self.actor_requested.emit(data[1])

    def open_inventory(self):
        data = self.selected()
        if data and data[2]:
            self.inventory_requested.emit(data[2])

    def delete_actor(self):
        data = self.selected()
        if data:
            self.delete_requested.emit(data[1])
