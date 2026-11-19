from collections.abc import Iterable

from PySide6.QtCore import QItemSelectionModel, QModelIndex, QPoint, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QInputDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.domain.card import Card
from lodandsy.domain.entity_summary import EntitySummary
from lodandsy.ui.card_creation_dialog import CardCreationDialog
from lodandsy.ui.card_tree_model import CARD_ID_ROLE
from lodandsy.ui.card_tree_view import CardTreeView
from lodandsy.ui.icons import icon
from lodandsy.ui.navigator_actions import NavigatorActions
from lodandsy.ui.project_tree_model import (
    NODE_ID_ROLE,
    NODE_KEY_ROLE,
    NODE_KIND_ROLE,
    ProjectTreeModel,
)


class TreePanel(QDockWidget):
    entity_selected = Signal(str, str)
    entity_open_requested = Signal(str, str)
    module_create_requested = Signal(str)
    module_rename_requested = Signal(str, str)
    module_delete_requested = Signal(str, str)
    search_requested = Signal()
    move_parent_requested = Signal(str)
    card_selected = Signal(str)
    card_open_requested = Signal(str)

    create_requested = Signal(str, object)
    template_create_requested = Signal(str, object, str)
    rename_requested = Signal(str, str)
    delete_requested = Signal(str)
    reparent_requested = Signal(str, object)
    move_requested = Signal(str, object, int)
    copy_link_requested = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Проект", parent)

        self.setObjectName("treePanel")
        self.map_creation_enabled = True
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.setFeatures(
            QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
        )

        self.tree_view = CardTreeView(self)
        self.tree_view.setObjectName("cardTreeView")
        self.tree_view.setHeaderHidden(True)

        self.tree_view.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.tree_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tree_view.setExpandsOnDoubleClick(False)

        self.tree_view.setDragEnabled(True)
        self.tree_view.setAcceptDrops(True)
        self.tree_view.setDropIndicatorShown(True)
        self.tree_view.setDragDropMode(
            QAbstractItemView.DragDropMode.DragDrop
        )
        self.tree_view.setDefaultDropAction(
            Qt.DropAction.MoveAction
        )

        self.tree_model = ProjectTreeModel(self)
        self.tree_view.setModel(self.tree_model)

        self.tree_view.selectionModel().currentChanged.connect(
            self._on_current_changed
        )
        self.tree_view.doubleClicked.connect(
            self._on_double_clicked
        )
        self.tree_view.open_requested.connect(self._on_double_clicked)

        self.tree_model.reparent_requested.connect(
            self.reparent_requested.emit
        )
        self.tree_model.move_requested.connect(self.move_requested.emit)

        self.tree_view.context_menu_requested.connect(
            self._show_context_menu
        )

        content = QWidget(self)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        toolbar = QToolBar(content)
        self.create_button = QToolButton(toolbar)
        self.create_button.setIcon(icon("plus"))
        self.create_button.setAccessibleName("Создать объект проекта")
        self.create_button.setToolTip("Создать объект проекта (Insert)")
        self.create_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.create_menu = self._creation_menu()
        self.create_button.setMenu(self.create_menu)
        self.search_button = QToolButton(toolbar)
        self.search_button.setIcon(icon("search"))
        self.search_button.setAccessibleName("Поиск карточек")
        self.search_button.setToolTip("Поиск карточек (Ctrl+F)")
        self.search_button.clicked.connect(self.search_requested)
        toolbar.addWidget(self.create_button)
        toolbar.addWidget(self.search_button)
        layout.addWidget(toolbar)
        layout.addWidget(self.tree_view)
        self.setWidget(content)
        self.inline_actions = NavigatorActions(self)
        QWidget.setTabOrder(self.create_button, self.search_button)
        QWidget.setTabOrder(self.search_button, self.tree_view)
        QWidget.setTabOrder(self.tree_view, self.inline_actions.open_button)
        QWidget.setTabOrder(self.inline_actions.open_button, self.inline_actions.menu_button)
        for shortcut, callback in [("F2", self.request_rename), ("Delete", self.request_delete),
                                   ("Insert", self.show_creation_menu),
                                   ("Shift+F10", self.show_selected_menu)]:
            key = QShortcut(QKeySequence(shortcut), self)
            key.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            key.activated.connect(callback)

    def _creation_menu(self):
        menu = QMenu(self)
        for kind, title in [("card", "Карточка…"), ("map", "Карта из изображения…"),
                            ("table", "Случайная таблица…")]:
            action = menu.addAction(title)
            action.setObjectName(f"create-{kind}")
            action.triggered.connect(lambda _checked=False, k=kind: self._create_kind(k))
        return menu

    def _create_kind(self, kind):
        if kind == "map" and not self.map_creation_enabled:
            return
        if kind == "card":
            self.request_create_root()
        else:
            self.module_create_requested.emit(kind)

    def show_creation_menu(self):
        self.create_menu.exec(self.create_button.mapToGlobal(self.create_button.rect().bottomLeft()))

    def show_selected_menu(self):
        index = self.tree_view.currentIndex()
        menu = self.context_menu(index)
        position = self.tree_view.visualRect(index).bottomLeft()
        try:
            menu.exec(self.tree_view.viewport().mapToGlobal(position))
        finally:
            menu.deleteLater()

    def set_map_creation_enabled(self, enabled):
        self.map_creation_enabled = enabled
        for action in self.create_menu.actions():
            if action.objectName() == "create-map":
                action.setEnabled(enabled)

    def set_cards(
        self,
        cards: Iterable[Card | EntitySummary],
    ) -> None:
        self._preserve_tree_state(lambda: self.tree_model.set_cards(cards))

    def set_modules(self, maps, tables):
        def update():
            self.tree_model.set_module_entries("map", maps)
            self.tree_model.set_module_entries("table", tables)
        self._preserve_tree_state(update)

    def current_node_key(self):
        return self.tree_view.currentIndex().data(NODE_KEY_ROLE)

    def expanded_keys(self):
        return [key for key in self.tree_model.node_keys()
                if self.tree_view.isExpanded(self.tree_model.index_for_node(key))]

    def _preserve_tree_state(self, update):
        selected = self.current_node_key()
        previous_selection = selected
        expanded = self.expanded_keys()
        previous_counts = {kind: self.tree_model.rowCount(self.tree_model.section_index(kind))
                           for kind in ("card", "map", "table")}
        scroll = self.tree_view.verticalScrollBar().value()
        blocker = QSignalBlocker(self.tree_view.selectionModel())
        update()
        for key in expanded:
            self.tree_view.setExpanded(self.tree_model.index_for_node(key), True)
        for kind in ("card", "map", "table"):
            if (previous_counts[kind] == 0
                    and self.tree_model.rowCount(self.tree_model.section_index(kind)) > 0):
                self.tree_view.setExpanded(self.tree_model.section_index(kind), True)
        if selected and not self.tree_model.index_for_node(selected).isValid():
            kind = selected.split(":", 1)[0]
            selected = f"section:{kind}" if kind in {"card", "map", "table"} else None
        self.select_node(selected)
        self.tree_view.verticalScrollBar().setValue(scroll)
        del blocker
        if previous_selection != self.current_node_key():
            self._on_current_changed(self.tree_view.currentIndex(), QModelIndex())
        self.inline_actions.select_current()

    def select_node(self, key):
        blocker = QSignalBlocker(self.tree_view.selectionModel())
        index = self.tree_model.index_for_node(key)
        self.tree_view.selectionModel().setCurrentIndex(
            index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        del blocker
        if hasattr(self, "inline_actions"):
            self.inline_actions.select_current()

    def select_card(self, card_id: str | None) -> None:
        self.select_node(f"card:{card_id}" if card_id is not None else None)

    def request_open(self, index=None):
        self._on_double_clicked(self._resolve_index(index))

    def request_create_root(self) -> None:
        self._request_create(parent_id=None)

    def request_create_child(
        self,
        index: QModelIndex | None = None,
    ) -> None:
        target_index = self._resolve_index(index)

        parent_id = self._card_id_from_index(
            target_index
        )

        if parent_id is None:
            return

        self._request_create(
            parent_id=parent_id
        )

    def request_rename(
        self,
        index: QModelIndex | None = None,
    ) -> None:
        target_index = self._resolve_index(index)
        if target_index.data(NODE_KIND_ROLE) in {"map", "table"}:
            self.module_rename_requested.emit(target_index.data(NODE_KIND_ROLE),
                                              target_index.data(NODE_ID_ROLE))
            return

        card_id = self._card_id_from_index(
            target_index
        )

        if card_id is None:
            return

        current_title = target_index.data()

        if not isinstance(current_title, str):
            return

        new_title, accepted = QInputDialog.getText(
            self,
            "Переименовать карточку",
            "Название:",
            QLineEdit.EchoMode.Normal,
            current_title,
        )

        if not accepted:
            return

        new_title = new_title.strip()

        if not new_title:
            return

        if new_title == current_title:
            return

        self.rename_requested.emit(
            card_id,
            new_title,
        )

    def request_delete(
        self,
        index: QModelIndex | None = None,
    ) -> None:
        target_index = self._resolve_index(index)

        if target_index.data(NODE_KIND_ROLE) in {"map", "table"}:
            self.module_delete_requested.emit(target_index.data(NODE_KIND_ROLE),
                                              target_index.data(NODE_ID_ROLE))
            return

        card_id = self._card_id_from_index(
            target_index
        )

        if card_id is None:
            return

        title = target_index.data()

        if not isinstance(title, str):
            return

        has_children = (
            self.tree_model.rowCount(target_index) > 0
        )

        if has_children:
            message = (
                f'Удалить «{title}» и все вложенные карточки?\n\n'
                "Будет удалено всё поддерево карточек."
            )
        else:
            message = f'Удалить «{title}»?'

        answer = QMessageBox.question(
            self,
            "Удаление карточки",
            message,
            (
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            ),
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.delete_requested.emit(card_id)

    def _request_create(
        self,
        parent_id: str | None,
    ) -> None:
        title, template_id, accepted = CardCreationDialog.get_card(self)

        if not accepted:
            return

        title = title.strip()

        if not title:
            return

        self.template_create_requested.emit(
            title,
            parent_id,
            template_id,
        )

    def _show_context_menu(
        self,
        index: QModelIndex,
        global_position: QPoint,
    ) -> None:
        if index.isValid():
            self.tree_view.setCurrentIndex(index)

        menu = self.context_menu(index)
        try:
            menu.exec(global_position)
        finally:
            menu.deleteLater()

    def context_menu(self, index=None):
        index = self._resolve_index(index)
        key = index.data(NODE_KEY_ROLE)
        kind, entity_id = index.data(NODE_KIND_ROLE), index.data(NODE_ID_ROLE)
        menu = QMenu(self)
        def command(name, title, callback):
            action = QAction(title, menu)
            action.setObjectName(name)
            action.triggered.connect(callback)
            menu.addAction(action)
            return action
        def current():
            return self.tree_model.index_for_node(key)
        if not index.isValid():
            for k, title in [("card", "Создать карточку…"), ("map", "Создать карту…"),
                             ("table", "Создать таблицу…")]:
                action = command(f"create-{k}", title,
                                 lambda _checked=False, k=k: self._create_kind(k))
                action.setEnabled(k != "map" or self.map_creation_enabled)
            command("dice", "Кубики", lambda: self.entity_open_requested.emit("dice", "dice"))
        elif kind == "section":
            action = command(f"create-{entity_id}", "Создать…",
                             lambda: self._create_kind(entity_id))
            action.setEnabled(entity_id != "map" or self.map_creation_enabled)
        else:
            command("open", "Открыть · Enter", lambda: self.request_open(current()))
            if kind == "dice":
                return menu
            if kind == "card":
                command("child", "Создать дочернюю карточку…",
                        lambda: self.request_create_child(current()))
                command("move-parent", "Переместить в…",
                        lambda: self.move_parent_requested.emit(entity_id))
                for direction, label in [(-1, "Выше"), (1, "Ниже")]:
                    def move(_checked=False, d=direction):
                        target = current()
                        if target.isValid():
                            self.move_requested.emit(entity_id, target.parent().data(CARD_ID_ROLE),
                                                     target.row() + d)
                    action = command(f"move-{direction}", label, move)
                    action.setEnabled(0 <= index.row() + direction
                                      < self.tree_model.rowCount(index.parent()))
                command("copy-link", "Копировать ссылку на карточку",
                        lambda: self.copy_link_requested.emit(entity_id))
            menu.addSeparator()
            command("rename", "Переименовать · F2", lambda: self.request_rename(current()))
            command("delete", "Удалить… · Delete", lambda: self.request_delete(current()))
        return menu

    def _on_current_changed(
        self,
        current: QModelIndex,
        _previous: QModelIndex,
    ) -> None:
        card_id = self._card_id_from_index(current)

        kind, entity_id = current.data(NODE_KIND_ROLE), current.data(NODE_ID_ROLE)
        if isinstance(kind, str) and isinstance(entity_id, str):
            self.entity_selected.emit(kind, entity_id)

        if card_id is not None:
            self.card_selected.emit(card_id)

    def _on_double_clicked(
        self,
        index: QModelIndex,
    ) -> None:
        card_id = self._card_id_from_index(index)

        kind, entity_id = index.data(NODE_KIND_ROLE), index.data(NODE_ID_ROLE)
        if kind == "section":
            self.tree_view.setExpanded(index, not self.tree_view.isExpanded(index))
        elif isinstance(kind, str) and isinstance(entity_id, str):
            self.entity_open_requested.emit(kind, entity_id)

        if card_id is not None:
            self.card_open_requested.emit(card_id)

    def _resolve_index(
        self,
        index: QModelIndex | None,
    ) -> QModelIndex:
        if index is not None:
            return index

        return self.tree_view.currentIndex()

    @staticmethod
    def _card_id_from_index(
        index: QModelIndex,
    ) -> str | None:
        if not index.isValid():
            return None

        card_id = index.data(CARD_ID_ROLE)

        if not isinstance(card_id, str):
            return None

        return card_id
