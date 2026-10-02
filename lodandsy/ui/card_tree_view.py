from PySide6.QtCore import QModelIndex, QPoint, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QDrag
from PySide6.QtWidgets import QTreeView


class CardTreeView(QTreeView):
    context_menu_requested = Signal(QModelIndex, QPoint)

    def startDrag(
        self,
        supported_actions: Qt.DropAction,
    ) -> None:
        del supported_actions

        indexes = [
            index
            for index in self.selectedIndexes()
            if index.column() == 0
        ]

        if not indexes:
            return

        model = self.model()

        if model is None:
            return

        mime_data = model.mimeData(indexes)

        if mime_data is None:
            return

        drag = QDrag(self)
        drag.setMimeData(mime_data)

        # Источник истины — CardCollection.
        # Сам Tree после drag строку не удаляет.
        drag.exec(Qt.DropAction.MoveAction)

    def contextMenuEvent(
        self,
        event: QContextMenuEvent,
    ) -> None:
        index = self.indexAt(event.pos())

        self.context_menu_requested.emit(
            index,
            event.globalPos(),
        )

        event.accept()