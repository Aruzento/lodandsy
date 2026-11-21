"""Shared typed field controls; emits edits, never owns canonical world values."""

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QWidget,
)

from lodandsy.domain.card_schema import field_definition
from lodandsy.ui.game_labels import choice_label, field_label
from lodandsy.ui.hit_history import HitHistoryEdit
from lodandsy.ui.semantic_edits import SemanticLineEdit


def field_text(value):
    return (
        ""
        if value is None
        else ", ".join(map(str, value))
        if isinstance(value, tuple)
        else str(value)
    )


class CardFieldsForm(QWidget):
    edited = Signal(object)
    edit_started = Signal(str)
    buffer_changed = Signal(str, str)
    commit_requested = Signal(str, str)
    cancel_requested = Signal(str)

    def __init__(self, parent=None, *, groups=True):
        super().__init__(parent)
        self.controls = {}
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.setMinimumWidth(0)
        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setSpacing(8)
        self.form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.keys = ()
        self.groups = groups
        self.edit_active = lambda key: False

    def set_card(self, card, keys, drafts=None):
        self.set_values(card.id, card.value, keys, drafts)

    def set_values(self, owner_id, read, keys, drafts=None):
        if self.keys != tuple(keys):
            while self.form.rowCount():
                self.form.removeRow(0)
            self.controls.clear()
            self.keys = tuple(keys)
            group = None
            for key in keys:
                definition = field_definition(key)
                if self.groups and definition.group != group:
                    group = definition.group
                    caption = QLabel(
                        {
                            "abilities": "ХАРАКТЕРИСТИКИ",
                            "resources": "РЕСУРСЫ",
                            "calculation": "РЕЖИМЫ РАСЧЁТА",
                            "character": "ПЕРСОНАЖ",
                            "skills": "НАВЫКИ: 0 / 1 / 2",
                            "saves": "СПАСБРОСКИ",
                            "hp_inputs": "ИСТОРИЯ HP",
                            "defence": "ЗАЩИТА",
                            "movement": "ДВИЖЕНИЕ",
                            "spell": "МАГИЯ",
                            "attack": "АТАКА",
                            "identity": "ИДЕНТИЧНОСТЬ",
                            "item": "ПРЕДМЕТ",
                        }.get(group, "СВОЙСТВА")
                    )
                    caption.setObjectName("sectionCaption")
                    self.form.addRow(caption)
                if definition.data_type == "bool":
                    widget = QCheckBox()
                    widget.setTristate(definition.nullable)
                    widget.checkStateChanged.connect(lambda state, k=key: self._boolean(k, state))
                elif definition.choices:
                    widget = QComboBox()
                    if definition.nullable:
                        widget.addItem("Не задано", None)
                    for choice in definition.choices:
                        widget.addItem(
                            choice_label(key, choice),
                            choice,
                        )
                    widget.currentIndexChanged.connect(
                        lambda index, k=key, w=widget: self.edited.emit({k: w.itemData(index)})
                    )
                else:
                    widget = HitHistoryEdit() if key == "hp_gains" else SemanticLineEdit()
                    if isinstance(widget, SemanticLineEdit):
                        widget.setMaxLength(
                            definition.max_length if definition.data_type == "text" else 2048
                        )
                        widget.setPlaceholderText("Не задано")
                    widget.edit_started.connect(lambda k=key: self.edit_started.emit(k))
                    widget.buffer_changed.connect(
                        lambda raw, k=key: self.buffer_changed.emit(k, raw)
                    )
                    widget.commit_requested.connect(
                        lambda raw, k=key: self.commit_requested.emit(k, raw)
                    )
                    widget.cancel_requested.connect(lambda k=key: self.cancel_requested.emit(k))
                widget.setObjectName("field_" + key)
                widget.setMinimumWidth(0)
                widget.setAccessibleName(field_label(key))
                widget.setToolTip(field_label(key))
                self.controls[key] = widget
                label = QLabel(field_label(key))
                label.setWordWrap(True)
                label.setBuddy(widget)
                self.form.addRow(label, widget)
        drafts = drafts or {}
        for key, widget in self.controls.items():
            value = read(key)
            raw = drafts.get((owner_id, key))
            blocker = QSignalBlocker(widget)
            if isinstance(widget, QCheckBox):
                widget.setCheckState(
                    Qt.CheckState.PartiallyChecked
                    if value is None
                    else Qt.CheckState.Checked
                    if value
                    else Qt.CheckState.Unchecked
                )
            elif isinstance(widget, (QLineEdit, HitHistoryEdit)):
                if isinstance(widget, HitHistoryEdit):
                    widget.level, widget.die = read("level") or 1, read("hit_die")
                text = raw if raw is not None else field_text(value)
                widget.set_value(text, force=not self.edit_active(key))
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(widget.findData(value))
            widget.setProperty("invalid", raw is not None)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            del blocker

    def set_field_visible(self, key, visible):
        widget = self.controls.get(key)
        if widget is not None:
            widget.setVisible(visible)
            self.form.labelForField(widget).setVisible(visible)

    def _boolean(self, key, state):
        self.edited.emit(
            {
                key: None
                if state == Qt.CheckState.PartiallyChecked
                else state == Qt.CheckState.Checked
            }
        )
