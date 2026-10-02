from collections.abc import Iterable

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFormLayout,
    QLineEdit,
    QWidget,
)


class InspectorPanel(QDockWidget):
    title_changed = Signal(str, str)
    parent_changed = Signal(str, object)

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Inspector", parent)

        self.setObjectName("inspectorPanel")
        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.setFeatures(
            QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
        )

        self._card_id: str | None = None
        self._title = ""

        content = QWidget(self)

        self.id_edit = QLineEdit(content)
        self.id_edit.setObjectName("inspectorId")
        self.id_edit.setReadOnly(True)

        self.title_edit = QLineEdit(content)
        self.title_edit.setObjectName("inspectorTitle")

        self.parent_combo = QComboBox(content)
        self.parent_combo.setObjectName("inspectorParent")

        form = QFormLayout(content)
        form.addRow("ID", self.id_edit)
        form.addRow("Title", self.title_edit)
        form.addRow("Parent", self.parent_combo)

        self.setWidget(content)

        self.title_edit.editingFinished.connect(
            self._on_title_editing_finished
        )
        self.parent_combo.currentIndexChanged.connect(
            self._on_parent_index_changed
        )

        self.clear_card()

    def set_card(
        self,
        card_id: str,
        title: str,
        parent_id: str | None,
        parent_options: Iterable[
            tuple[str | None, str]
        ],
    ) -> None:
        self._card_id = card_id
        self._title = title

        id_blocker = QSignalBlocker(self.id_edit)
        title_blocker = QSignalBlocker(self.title_edit)
        parent_blocker = QSignalBlocker(
            self.parent_combo
        )

        self.id_edit.setText(card_id)
        self.title_edit.setText(title)

        self.parent_combo.clear()

        selected_index = -1

        for option_id, option_title in parent_options:
            self.parent_combo.addItem(
                option_title,
                option_id,
            )

            if option_id == parent_id:
                selected_index = (
                    self.parent_combo.count() - 1
                )

        if selected_index >= 0:
            self.parent_combo.setCurrentIndex(
                selected_index
            )

        self.id_edit.setEnabled(True)
        self.title_edit.setEnabled(True)
        self.parent_combo.setEnabled(True)

        del id_blocker
        del title_blocker
        del parent_blocker

    def clear_card(self) -> None:
        self._card_id = None
        self._title = ""

        id_blocker = QSignalBlocker(self.id_edit)
        title_blocker = QSignalBlocker(self.title_edit)
        parent_blocker = QSignalBlocker(
            self.parent_combo
        )

        self.id_edit.clear()
        self.title_edit.clear()
        self.parent_combo.clear()

        self.id_edit.setEnabled(False)
        self.title_edit.setEnabled(False)
        self.parent_combo.setEnabled(False)

        del id_blocker
        del title_blocker
        del parent_blocker

    def _on_title_editing_finished(self) -> None:
        if self._card_id is None:
            return

        new_title = self.title_edit.text().strip()

        if not new_title:
            blocker = QSignalBlocker(
                self.title_edit
            )
            self.title_edit.setText(
                self._title
            )
            del blocker
            return

        if new_title == self._title:
            return

        self._title = new_title

        self.title_changed.emit(
            self._card_id,
            new_title,
        )

    def _on_parent_index_changed(
        self,
        index: int,
    ) -> None:
        if self._card_id is None:
            return

        if index < 0:
            return

        parent_id = self.parent_combo.itemData(
            index
        )

        if (
            parent_id is not None
            and not isinstance(parent_id, str)
        ):
            return

        self.parent_changed.emit(
            self._card_id,
            parent_id,
        )