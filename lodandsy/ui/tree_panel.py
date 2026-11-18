from collections.abc import Iterable

from PySide6.QtCore import QItemSelectionModel, QModelIndex, QPoint, QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QInputDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
    QWidget,
)

from lodandsy.domain.card import Card
from lodandsy.domain.entity_summary import EntitySummary
from lodandsy.ui.card_tree_model import (
    CARD_ID_ROLE,
    CardTreeModel,
)
from lodandsy.ui.card_tree_view import CardTreeView


class TreePanel(QDockWidget):
    card_selected = Signal(str)
    card_open_requested = Signal(str)

    create_requested = Signal(str, object)
    rename_requested = Signal(str, str)
    delete_requested = Signal(str)
    reparent_requested = Signal(str, object)
    move_requested = Signal(str, object, int)
    copy_link_requested = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Tree", parent)

        self.setObjectName("treePanel")
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

        self.tree_model = CardTreeModel(self)
        self.tree_view.setModel(self.tree_model)

        self.tree_view.selectionModel().currentChanged.connect(
            self._on_current_changed
        )
        self.tree_view.doubleClicked.connect(
            self._on_double_clicked
        )

        self.tree_model.reparent_requested.connect(
            self.reparent_requested.emit
        )
        self.tree_model.move_requested.connect(self.move_requested.emit)

        self.tree_view.context_menu_requested.connect(
            self._show_context_menu
        )

        self.setWidget(self.tree_view)

    def set_cards(
        self,
        cards: Iterable[Card | EntitySummary],
    ) -> None:
        selected_id = self._card_id_from_index(self.tree_view.currentIndex())
        old_ids = self.tree_model.card_ids()
        expanded_ids = {
            card_id for card_id in old_ids
            if self.tree_view.isExpanded(self.tree_model.index_for_card(card_id))
        }
        scroll = self.tree_view.verticalScrollBar().value()
        blocker = QSignalBlocker(self.tree_view.selectionModel())
        self.tree_model.set_cards(cards)
        if not old_ids:
            self.tree_view.expandAll()
        else:
            for card_id in expanded_ids:
                self.tree_view.setExpanded(self.tree_model.index_for_card(card_id), True)
        self.select_card(selected_id)
        self.tree_view.verticalScrollBar().setValue(scroll)
        del blocker

    def select_card(self, card_id: str | None) -> None:
        blocker = QSignalBlocker(self.tree_view.selectionModel())
        index = (
            self.tree_model.index_for_card(card_id)
            if card_id is not None else QModelIndex()
        )
        self.tree_view.selectionModel().setCurrentIndex(
            index, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )
        del blocker

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
            "Rename card",
            "Title:",
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
                f'Delete "{title}" and all nested cards?\n\n'
                "All child cards and their descendants "
                "will also be deleted."
            )
        else:
            message = f'Delete "{title}"?'

        answer = QMessageBox.question(
            self,
            "Delete card",
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
        title, accepted = QInputDialog.getText(
            self,
            "Create card",
            "Title:",
        )

        if not accepted:
            return

        title = title.strip()

        if not title:
            return

        self.create_requested.emit(
            title,
            parent_id,
        )

    def _show_context_menu(
        self,
        index: QModelIndex,
        global_position: QPoint,
    ) -> None:
        if index.isValid():
            self.tree_view.setCurrentIndex(index)

        menu = QMenu(self)

        create_root_action = menu.addAction(
            "New root card"
        )

        create_child_action = None
        rename_action = None
        delete_action = None
        copy_link_action = None

        if index.isValid():
            menu.addSeparator()

            create_child_action = menu.addAction(
                "New child card"
            )

            rename_action = menu.addAction(
                "Rename"
            )

            delete_action = menu.addAction(
                "Delete"
            )
            copy_link_action = menu.addAction("Копировать ссылку на карточку")

        up_action = down_action = None
        if index.isValid():
            menu.addSeparator()
            up_action = menu.addAction("Move up")
            down_action = menu.addAction("Move down")
            up_action.setEnabled(index.row() > 0)
            down_action.setEnabled(index.row() + 1 < self.tree_model.rowCount(index.parent()))

        selected_action = menu.exec(
            global_position
        )

        if selected_action is create_root_action:
            self.request_create_root()
            return

        if selected_action is create_child_action:
            self.request_create_child(index)
            return

        if selected_action is rename_action:
            self.request_rename(index)
            return

        if selected_action is delete_action:
            self.request_delete(index)
        elif copy_link_action is not None and selected_action is copy_link_action:
            self.copy_link_requested.emit(self._card_id_from_index(index))
        elif selected_action is up_action and up_action is not None:
            self.move_requested.emit(
                self._card_id_from_index(index), self._card_id_from_index(index.parent()),
                index.row() - 1,
            )
        elif selected_action is down_action and down_action is not None:
            self.move_requested.emit(
                self._card_id_from_index(index), self._card_id_from_index(index.parent()),
                index.row() + 1,
            )

    def _on_current_changed(
        self,
        current: QModelIndex,
        _previous: QModelIndex,
    ) -> None:
        card_id = self._card_id_from_index(current)

        if card_id is not None:
            self.card_selected.emit(card_id)

    def _on_double_clicked(
        self,
        index: QModelIndex,
    ) -> None:
        card_id = self._card_id_from_index(index)

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
