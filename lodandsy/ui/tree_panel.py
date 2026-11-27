from PySide6.QtCore import (
    QItemSelectionModel,
    QModelIndex,
    QSignalBlocker,
    QSize,
    Qt,
    Signal,
)
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

from lodandsy.ui.card_creation_dialog import CardCreationDialog
from lodandsy.ui.card_tree_view import CardTreeView
from lodandsy.ui.icons import icon
from lodandsy.ui.navigator_actions import NavigatorActions
from lodandsy.ui.project_tree_model import (
    NODE_ID_ROLE,
    NODE_KEY_ROLE,
    NODE_KIND_ROLE,
    ProjectTreeModel,
)
from lodandsy.ui.theme import ICON_SIZE


class TreePanel(QDockWidget):
    entity_selected = Signal(str, str)
    entity_open_requested = Signal(str, str)
    map_editor_requested = Signal(str)
    module_create_requested = Signal(str, object)
    module_rename_requested = Signal(str, str)
    module_delete_requested = Signal(str, str)
    search_requested = Signal()
    move_parent_requested = Signal(str)

    create_requested = Signal(str, object)
    typed_create_requested = Signal(str, object, str)
    player_create_requested = Signal(str, object, str)
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

        self.deletion_reference_count = lambda ids: 0
        self.deletion_details = lambda ids: ""
        self.setObjectName("treePanel")
        self.map_creation_enabled = True
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)

        self.tree_view = CardTreeView(self)
        self.tree_view.setObjectName("cardTreeView")
        self.tree_view.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.tree_view.setHeaderHidden(True)

        self.tree_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree_view.setExpandsOnDoubleClick(False)

        self.tree_view.setDragEnabled(True)
        self.tree_view.setAcceptDrops(True)
        self.tree_view.setDropIndicatorShown(True)
        self.tree_view.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.tree_view.setDefaultDropAction(Qt.DropAction.MoveAction)

        self.tree_model = ProjectTreeModel(self)
        self.tree_view.setModel(self.tree_model)

        self.tree_view.selectionModel().currentChanged.connect(self._on_current_changed)
        self.tree_view.doubleClicked.connect(self._on_double_clicked)
        self.tree_view.open_requested.connect(self._on_double_clicked)

        self.tree_model.reparent_requested.connect(self.reparent_requested.emit)
        self.tree_model.move_requested.connect(self.move_requested.emit)

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
        self.search_button.setAccessibleName("Поиск документов")
        self.search_button.setToolTip("Поиск документов (Ctrl+F)")
        self.search_button.clicked.connect(self.search_requested)
        toolbar.addWidget(self.create_button)
        toolbar.addWidget(self.search_button)
        layout.addWidget(toolbar)
        layout.addWidget(self.tree_view)
        self.setWidget(content)
        self.inline_actions = NavigatorActions(self)
        self.tree_view.context_menu_requested.connect(self.inline_actions.show_menu)
        QWidget.setTabOrder(self.create_button, self.search_button)
        QWidget.setTabOrder(self.search_button, self.tree_view)
        for shortcut, callback in [
            ("F2", self.request_rename),
            ("Delete", self.request_delete),
            ("Insert", self.show_creation_menu),
            ("Shift+F10", self.show_selected_menu),
        ]:
            key = QShortcut(QKeySequence(shortcut), self)
            key.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            key.activated.connect(callback)

    def _creation_menu(self, parent_id=None, *, parent=None):
        menu = QMenu(self if parent is None else parent)
        for kind, title in [
            ("card", "Карточка…"),
            ("map", "Карта из изображения…"),
            ("table", "Таблица…"),
        ]:
            action = menu.addAction(title)
            action.setObjectName(f"create-{kind}")
            action.triggered.connect(lambda _checked=False, k=kind: self._create_kind(k, parent_id))
        return menu

    def _create_kind(self, kind, parent_id=None):
        if kind == "map" and not self.map_creation_enabled:
            return
        if kind == "card":
            self._request_create(parent_id)
        else:
            self.module_create_requested.emit(kind, parent_id)

    def show_creation_menu(self):
        self.create_menu.exec(
            self.create_button.mapToGlobal(self.create_button.rect().bottomLeft())
        )

    def show_selected_menu(self):
        index = self.tree_view.currentIndex()
        position = self.tree_view.visualRect(index).bottomLeft()
        self.inline_actions.show_menu(index, self.tree_view.viewport().mapToGlobal(position))

    def set_map_creation_enabled(self, enabled):
        self.map_creation_enabled = enabled
        for action in self.create_menu.actions():
            if action.objectName() == "create-map":
                action.setEnabled(enabled)

    def set_entities(self, entities, *, card_types=None):
        self._preserve_tree_state(
            lambda: self.tree_model.set_entities(entities, card_types=card_types)
        )

    def current_node_key(self):
        return self.tree_view.currentIndex().data(NODE_KEY_ROLE)

    def expanded_keys(self):
        return [
            key
            for key in self.tree_model.node_keys()
            if self.tree_view.isExpanded(self.tree_model.index_for_node(key))
        ]

    def _preserve_tree_state(self, update):
        selected = self.current_node_key()
        previous_selection = selected
        expanded = self.expanded_keys()
        scroll = self.tree_view.verticalScrollBar().value()
        blocker = QSignalBlocker(self.tree_view.selectionModel())
        update()
        for key in expanded:
            self.tree_view.setExpanded(self.tree_model.index_for_node(key), True)
        if selected and not self.tree_model.index_for_node(selected).isValid():
            selected = None
        self.select_node(selected)
        self.tree_view.verticalScrollBar().setValue(scroll)
        del blocker
        if previous_selection != self.current_node_key():
            self._on_current_changed(self.tree_view.currentIndex(), QModelIndex())

    def select_node(self, key):
        blocker = QSignalBlocker(self.tree_view.selectionModel())
        index = self.tree_model.index_for_node(key)
        self.tree_view.selectionModel().setCurrentIndex(
            index, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )
        del blocker

    def request_open(self, index=None):
        self._on_double_clicked(self._resolve_index(index))

    def request_create_root(self) -> None:
        self._request_create(parent_id=None)

    def request_create_child(
        self,
        index: QModelIndex | None = None,
    ) -> None:
        target_index = self._resolve_index(index)

        parent_id = target_index.data(NODE_ID_ROLE)

        if parent_id is None:
            return

        self._request_create(parent_id=parent_id)

    def request_rename(
        self,
        index: QModelIndex | None = None,
    ) -> None:
        target_index = self._resolve_index(index)
        card_id = target_index.data(NODE_ID_ROLE)
        if card_id is None:
            return

        current_title = target_index.data()

        if not isinstance(current_title, str):
            return

        new_title, accepted = QInputDialog.getText(
            self,
            "Переименовать документ",
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

        card_id = target_index.data(NODE_ID_ROLE)
        if card_id is None:
            return
        counts, pending = {}, [target_index]
        deleting_ids = set()
        while pending:
            current = pending.pop()
            deleting_ids.add(current.data(NODE_ID_ROLE))
            kind = current.data(NODE_KIND_ROLE)
            counts[kind] = counts.get(kind, 0) + 1
            pending.extend(
                self.tree_model.index(row, 0, current)
                for row in range(self.tree_model.rowCount(current))
            )
        labels = {"card": "карточек", "map": "карт", "table": "таблиц"}
        details = ", ".join(f"{labels[kind]}: {count}" for kind, count in counts.items())
        title = target_index.data()
        message = (
            f"Удалить «{title}» и вложенные документы?\n\n"
            f"Всего: {sum(counts.values())} ({details}).\n"
            "Окна удаляемых документов будут закрыты. "
            "Ссылки из других документов останутся."
        )

        placements = self.deletion_reference_count(deleting_ids)
        message += self.deletion_details(deleting_ids)
        if placements:
            message += (
                f"\n\nРазмещений токенов: {placements}. Они будут удалены вместе "
                "с карточками. Остальные карточки сохранятся."
            )

        answer = QMessageBox.question(
            self,
            "Удаление документов",
            message,
            (QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No),
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.delete_requested.emit(card_id)

    def _request_create(
        self,
        parent_id: str | None,
    ) -> None:
        title, card_type, player, accepted = CardCreationDialog.get_card(self)

        if not accepted:
            return

        title = title.strip()

        if not title:
            return

        signal = self.player_create_requested if player else self.typed_create_requested
        signal.emit(
            title,
            parent_id,
            card_type,
        )

    def context_menu(self, index=None):
        index = self._resolve_index(index)
        key = index.data(NODE_KEY_ROLE)
        entity_id = index.data(NODE_ID_ROLE)
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
            for k, title in [
                ("card", "Создать карточку…"),
                ("map", "Создать карту…"),
                ("table", "Создать таблицу…"),
            ]:
                action = command(
                    f"create-{k}", title, lambda _checked=False, k=k: self._create_kind(k)
                )
                action.setEnabled(k != "map" or self.map_creation_enabled)
        else:
            command("open", "Открыть · Enter", lambda: self.request_open(current()))
            if index.data(NODE_KIND_ROLE) == "map":
                menu.addAction(
                    "Открыть редактор карты", lambda: self.map_editor_requested.emit(entity_id)
                )
            child_menu = self._creation_menu(entity_id, parent=menu)
            child_menu.setTitle("Создать дочерний документ")
            menu.addMenu(child_menu).setObjectName("child")
            command(
                "move-parent", "Переместить в…", lambda: self.move_parent_requested.emit(entity_id)
            )
            for direction, label in [(-1, "Выше"), (1, "Ниже")]:

                def move(_checked=False, d=direction):
                    target = current()
                    if target.isValid():
                        self.move_requested.emit(
                            entity_id, target.parent().data(NODE_ID_ROLE), target.row() + d
                        )

                action = command(f"move-{direction}", label, move)
                action.setEnabled(
                    0 <= index.row() + direction < self.tree_model.rowCount(index.parent())
                )
            command(
                "copy-link",
                "Копировать ссылку на документ",
                lambda: self.copy_link_requested.emit(entity_id),
            )
            menu.addSeparator()
            command("rename", "Переименовать · F2", lambda: self.request_rename(current()))
            command("delete", "Удалить… · Delete", lambda: self.request_delete(current()))
        return menu

    def _on_current_changed(
        self,
        current: QModelIndex,
        _previous: QModelIndex,
    ) -> None:
        kind, entity_id = current.data(NODE_KIND_ROLE), current.data(NODE_ID_ROLE)
        if isinstance(kind, str) and isinstance(entity_id, str):
            self.entity_selected.emit(kind, entity_id)

    def _on_double_clicked(
        self,
        index: QModelIndex,
    ) -> None:
        kind, entity_id = index.data(NODE_KIND_ROLE), index.data(NODE_ID_ROLE)
        if isinstance(kind, str) and isinstance(entity_id, str):
            self.entity_open_requested.emit(kind, entity_id)

    def _resolve_index(
        self,
        index: QModelIndex | None,
    ) -> QModelIndex:
        if index is not None:
            return index

        return self.tree_view.currentIndex()
