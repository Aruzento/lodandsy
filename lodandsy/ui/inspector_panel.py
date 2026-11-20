from collections.abc import Iterable

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QWidget,
)

from lodandsy.application.clipboard import copy_text
from lodandsy.domain.card_schema import CARD_TYPES
from lodandsy.ui.card_fields import CardFieldsForm
from lodandsy.ui.conflict_bar import ConflictBar
from lodandsy.ui.icons import icon
from lodandsy.ui.semantic_edits import SemanticLineEdit


class InspectorPanel(QDockWidget):
    title_changed = Signal(str, str)
    parent_changed = Signal(str, object)
    fields_changed = Signal(str, object)
    add_field_requested = Signal()
    discard_drafts_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Свойства", parent)

        self.setObjectName("inspectorPanel")
        self.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)

        self._card_id: str | None = None
        self._title = ""

        content = QWidget(self)

        self.id_edit = QLineEdit(content)
        self.id_edit.setObjectName("inspectorId")
        self.id_edit.setReadOnly(True)

        self.title_edit = SemanticLineEdit(content)
        self.title_active = lambda: False
        self.title_edit.setObjectName("inspectorTitle")

        self.parent_combo = QComboBox(content)
        self.parent_combo.setObjectName("inspectorParent")

        form = QFormLayout(content)
        form.setContentsMargins(16, 12, 16, 16)
        form.setSpacing(10)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.id_edit.hide()
        title_row = QHBoxLayout()
        title_row.addWidget(self.title_edit, 1)
        details = QToolButton()
        details.setIcon(icon("more"))
        details.setToolTip("Идентификатор документа")
        menu = QMenu(details)
        menu.addAction("Копировать UUID", lambda: copy_text(self.id_edit.text()))
        details.setMenu(menu)
        details.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        title_row.addWidget(details)
        form.addRow(title_row)
        self.type_label = QLabel()
        self.type_label.setObjectName("mutedCaption")
        form.addRow(self.type_label)
        self.validation_notice = QLabel()
        self.validation_notice.setTextFormat(Qt.TextFormat.PlainText)
        self.validation_notice.setWordWrap(True)
        self.validation_notice.setObjectName("errorNotice")
        self.validation_notice.hide()
        form.addRow(self.validation_notice)
        self.fields_caption = QLabel("ХАРАКТЕРИСТИКИ")
        self.fields_caption.setObjectName("sectionCaption")
        form.addRow(self.fields_caption)
        self.field_form = CardFieldsForm()
        self.field_form.edited.connect(
            lambda changes: (
                self.fields_changed.emit(self._card_id, changes) if self._card_id else None
            )
        )
        form.addRow(self.field_form)
        self.add_field = QPushButton("Добавить поле…")
        self.add_field.clicked.connect(self.add_field_requested)
        self.discard = QPushButton("Отменить ошибочный ввод")
        self.discard.clicked.connect(self.discard_drafts_requested)
        form.addRow(self.add_field)
        form.addRow(self.discard)
        self.conflicts = ConflictBar(self)
        form.addRow(self.conflicts)
        organization = QLabel("ОРГАНИЗАЦИЯ")
        organization.setObjectName("sectionCaption")
        form.addRow(organization)
        form.addRow("Родитель", self.parent_combo)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)

        self.pages = QStackedWidget()
        self.pages.addWidget(scroll)
        empty = QLabel("Выберите объект\nв дереве проекта")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setObjectName("emptyInspector")
        self.pages.addWidget(empty)
        self.setWidget(self.pages)

        self.title_edit.commit_requested.connect(lambda raw: self._on_title_editing_finished())
        self.parent_combo.currentIndexChanged.connect(self._on_parent_index_changed)

        self.clear_card()

    def set_metadata(self, card, drafts):
        from lodandsy.domain.card_schema import field_definition

        keys = [*CARD_TYPES[card.card_type].fields]
        keys += [
            key
            for key, value in card.values
            if field_definition(key).group in {"general", "links", "presentation"}
            and key not in {"summary", "aliases"}
        ]
        self.field_form.set_card(card, tuple(dict.fromkeys(keys)), drafts)
        self.type_label.setText(CARD_TYPES[card.card_type].title)
        self.fields_caption.setVisible(bool(keys))
        self.field_form.show()
        self.add_field.show()
        self.discard.setVisible(any(key[0] == card.id for key in drafts))
        raw = drafts.get((card.id, "title"))
        if raw is not None:
            blocker = QSignalBlocker(self.title_edit)
            self.title_edit.set_value(raw, force=not self.title_active())
            del blocker

    def clear_metadata(self):
        self.type_label.clear()
        self.fields_caption.hide()
        self.field_form.hide()
        self.add_field.hide()
        self.discard.hide()

    def set_card(
        self,
        card_id: str,
        title: str,
        parent_id: str | None,
        parent_options: Iterable[tuple[str | None, str]],
    ) -> None:
        self.pages.setCurrentIndex(0)
        self._card_id = card_id
        self.title_edit.setReadOnly(False)
        self._title = title

        id_blocker = QSignalBlocker(self.id_edit)
        title_blocker = QSignalBlocker(self.title_edit)
        parent_blocker = QSignalBlocker(self.parent_combo)

        self.id_edit.setText(card_id)
        self.title_edit.set_value(title, force=not self.title_active())

        self.parent_combo.clear()

        selected_index = -1

        for option_id, option_title in parent_options:
            self.parent_combo.addItem(
                option_title,
                option_id,
            )

            if option_id == parent_id:
                selected_index = self.parent_combo.count() - 1

        if selected_index >= 0:
            self.parent_combo.setCurrentIndex(selected_index)

        self.id_edit.setEnabled(True)
        self.title_edit.setEnabled(True)
        self.parent_combo.setEnabled(True)

        del id_blocker
        del title_blocker
        del parent_blocker

    def show_entity_summary(self, entity_id, title):
        self.clear_card()
        self.id_edit.setText(entity_id)
        self.title_edit.setText(title)
        self.id_edit.setEnabled(True)
        self.title_edit.setEnabled(True)
        self.title_edit.setReadOnly(True)

    def clear_card(self) -> None:
        self.pages.setCurrentIndex(1)
        self.clear_metadata()
        self._card_id = None
        self._title = ""

        id_blocker = QSignalBlocker(self.id_edit)
        title_blocker = QSignalBlocker(self.title_edit)
        parent_blocker = QSignalBlocker(self.parent_combo)

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

        new_title = self.title_edit.text()

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

        parent_id = self.parent_combo.itemData(index)

        if parent_id is not None and not isinstance(parent_id, str):
            return

        self.parent_changed.emit(
            self._card_id,
            parent_id,
        )
