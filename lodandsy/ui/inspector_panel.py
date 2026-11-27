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
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.application.clipboard import copy_text
from lodandsy.domain.card_schema import ACTOR_TYPES, CARD_TYPES, field_definition, permitted_fields
from lodandsy.ui.card_fields import CardFieldsForm
from lodandsy.ui.conflict_bar import ConflictBar
from lodandsy.ui.game_labels import error_text, field_label, field_surface, source_text, value_text
from lodandsy.ui.icons import icon
from lodandsy.ui.semantic_edits import SemanticLineEdit


class InspectorPanel(QDockWidget):
    title_changed = Signal(str, str)
    parent_changed = Signal(str, object)
    fields_changed = Signal(str, object)
    add_field_requested = Signal()
    discard_drafts_requested = Signal()
    base_requested = Signal()
    inventory_requested = Signal()
    sheet_requested = Signal()

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
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
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
        self.actor_summary = QLabel()
        self.actor_summary.setWordWrap(True)
        self.actor_summary.hide()
        form.addRow(self.actor_summary)
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
        self.details_tabs = QTabWidget()
        self.details_tabs.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.details_tabs.addTab(self.field_form, "Свойства")
        effective = QWidget()
        self.effective_form = QFormLayout(effective)
        self.effective_labels = {}
        self.details_tabs.addTab(effective, "Расчёты")
        form.addRow(self.details_tabs)
        self.base_button = QPushButton("Базовая карточка")
        self.base_button.clicked.connect(self.base_requested)
        self.inventory_button = QPushButton("Индивидуальный инвентарь")
        self.inventory_button.clicked.connect(self.inventory_requested)
        self.sheet_button = QPushButton("Открыть характеристики")
        self.sheet_button.clicked.connect(self.sheet_requested)
        form.addRow(self.base_button)
        form.addRow(self.inventory_button)
        form.addRow(self.sheet_button)
        self.base_button.hide()
        self.inventory_button.hide()
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
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.pages = QStackedWidget()
        self.pages.addWidget(scroll)
        empty = QLabel("Выберите объект\nв дереве проекта")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setObjectName("emptyInspector")
        self.pages.addWidget(empty)
        container = QWidget()
        self.panel_layout = QVBoxLayout(container)
        self.panel_layout.setContentsMargins(0, 0, 0, 0)
        self.panel_layout.setSpacing(0)
        self.panel_layout.addWidget(self.pages, 1)
        self.context_control = None
        self.setWidget(container)

        self.title_edit.commit_requested.connect(lambda raw: self._on_title_editing_finished())
        self.parent_combo.currentIndexChanged.connect(self._on_parent_index_changed)
        self.details_tabs.currentChanged.connect(self._size_details)

        self.clear_card()

    def _size_details(self, *_args):
        form = (
            self.field_form
            if self.details_tabs.currentIndex() == 0
            else self.details_tabs.widget(1)
        )
        self.details_tabs.setMaximumHeight(form.sizeHint().height() + 80)

    def set_metadata(self, card, drafts):
        self.fields_caption.setText("СВОЙСТВА")
        keys = [
            key for key in CARD_TYPES[card.card_type].fields if field_surface(key) == "inspector"
        ]
        keys += [
            key
            for key, value in card.values
            if field_definition(key).group in {"general", "links", "presentation"}
            and key not in {"summary", "aliases"}
        ]
        keys = [key for key in keys if key != "modifiers"]
        self.field_form.set_card(card, tuple(dict.fromkeys(keys)), drafts)
        self.details_tabs.setVisible(bool(keys))
        self.details_tabs.setMaximumHeight(self.field_form.sizeHint().height() + 45)
        self.actor_summary.hide()
        self.details_tabs.setTabVisible(1, False)
        self.sheet_button.setVisible(card.card_type in ACTOR_TYPES or card.card_type == "item")
        self.sheet_button.setText(
            "Открыть модификаторы" if card.card_type == "item" else "Открыть характеристики"
        )
        self.base_button.hide()
        self.inventory_button.hide()
        self.parent_combo.setEnabled(True)
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

    def set_actor_metadata(self, card, actor, drafts):
        keys = [
            key
            for key in ("hp_current", "hp_temp", "ac_override", "hp_max_override", "speed_override")
            if key in permitted_fields(card.card_type, "actor")
        ]
        self.field_form.set_values(actor.id, actor.value, keys, drafts)
        self.details_tabs.show()
        self._size_details()
        self.actor_summary.show()
        self.details_tabs.setTabVisible(1, True)
        self.sheet_button.show()
        self.sheet_button.setText("Открыть игровой лист")
        self.type_label.setText("Участник · " + card.title)
        self.fields_caption.setText("ИНДИВИДУАЛЬНЫЕ ЗНАЧЕНИЯ")
        self.fields_caption.show()
        self.field_form.show()
        self.add_field.hide()
        self.base_button.show()
        self.inventory_button.setVisible(actor.inventory_id is not None)
        self.parent_combo.setEnabled(False)

    def set_effective(self, effective, card_type, *, feet_per_cell=None):
        self.actor_summary.setText(
            "Хиты: "
            + value_text(effective.get("hp_current"))
            + " / "
            + value_text(effective.get("hp_max"))
            + " · КД: "
            + value_text(effective.get("ac"))
        )
        keys = tuple(effective.automatic)
        if card_type == "object":
            keys = tuple(
                key
                for key in keys
                if key
                in {
                    "hp_max",
                    "ac",
                    "speed",
                    "carried_weight",
                }
            )
        if tuple(self.effective_labels) != keys:
            while self.effective_form.rowCount():
                self.effective_form.removeRow(0)
            self.effective_labels.clear()
            for key in keys:
                label = QLabel()
                label.setTextFormat(Qt.TextFormat.PlainText)
                label.setWordWrap(True)
                label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                self.effective_labels[key] = label
                self.effective_form.addRow(field_label(key), label)
        for key, label in self.effective_labels.items():
            value, automatic = effective.get(key), effective.automatic[key]
            label.setText(value_text(value) + " · " + source_text(value.source))
            label.setToolTip(
                error_text(value.diagnostic)
                + "\nАвтоматически: "
                + (
                    str(automatic.value)
                    if automatic.status == "ok"
                    else value_text(automatic) + ": " + error_text(automatic.diagnostic)
                )
                + "\nЗависимости: "
                + ", ".join(field_label(str(key)) for key in sorted(value.dependencies, key=str))
            )
            if key == "speed" and value.status == "ok":
                conversion = f"{value.value} фт. · {value.value * 0.3048:g} м"
                if feet_per_cell is not None:
                    conversion += f" · {value.value / feet_per_cell:g} клеток"
                else:
                    conversion += " · масштаб карты не задан"
                label.setToolTip(label.toolTip() + "\n" + conversion)
        self._size_details()

    def clear_metadata(self):
        self.type_label.clear()
        self.fields_caption.hide()
        self.field_form.hide()
        self.add_field.hide()
        self.discard.hide()
        self.details_tabs.hide()
        self.base_button.hide()
        self.inventory_button.hide()
        self.sheet_button.hide()
        self.actor_summary.hide()

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

    @property
    def feature_page_active(self):
        return self.pages.currentIndex() > 1

    def clear_feature_page(self):
        if self.feature_page_active:
            self.pages.setCurrentIndex(1)

    def show_feature_page(self, widget):
        """Display a feature-owned native panel without transferring data ownership."""
        if self.pages.indexOf(widget) < 0:
            self.pages.addWidget(widget)
        self.pages.setCurrentWidget(widget)

    def show_context_control(self, widget):
        if widget is self.context_control:
            return
        if self.context_control is not None:
            self.panel_layout.removeWidget(self.context_control)
            self.context_control.hide()
        self.context_control = widget
        if widget is not None:
            self.panel_layout.addWidget(widget)
            widget.show()

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
