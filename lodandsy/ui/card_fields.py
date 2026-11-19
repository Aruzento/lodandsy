"""Shared typed field controls; emits edits, never owns canonical world values."""

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QCheckBox, QFormLayout, QLineEdit, QWidget

from lodandsy.domain.card_schema import field_definition
from lodandsy.ui.semantic_edits import SemanticLineEdit


def field_text(value):
    return "" if value is None else ", ".join(value) if isinstance(value, tuple) else str(value)


class CardFieldsForm(QWidget):
    edited = Signal(object)
    edit_started = Signal(str)
    buffer_changed = Signal(str, str)
    commit_requested = Signal(str, str)
    cancel_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.controls = {}
        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setSpacing(8)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.keys = ()
        self.edit_active = lambda key: False

    def set_card(self, card, keys, drafts=None):
        if self.keys != tuple(keys):
            while self.form.rowCount():
                self.form.removeRow(0)
            self.controls.clear()
            self.keys = tuple(keys)
            for key in keys:
                definition = field_definition(key)
                if definition.data_type == "bool":
                    widget = QCheckBox()
                    widget.setTristate(True)
                    widget.checkStateChanged.connect(lambda state, k=key: self._boolean(k, state))
                else:
                    widget = SemanticLineEdit()
                    widget.setMaxLength(
                        definition.max_length if definition.data_type == "text" else 2048
                    )
                    widget.setPlaceholderText("—")
                    widget.edit_started.connect(lambda k=key: self.edit_started.emit(k))
                    widget.buffer_changed.connect(
                        lambda raw, k=key: self.buffer_changed.emit(k, raw)
                    )
                    widget.commit_requested.connect(
                        lambda raw, k=key: self.commit_requested.emit(k, raw)
                    )
                    widget.cancel_requested.connect(lambda k=key: self.cancel_requested.emit(k))
                widget.setObjectName("field_" + key)
                widget.setAccessibleName(definition.label)
                widget.setToolTip(definition.hint or definition.label)
                self.controls[key] = widget
                self.form.addRow(definition.label, widget)
        drafts = drafts or {}
        for key, widget in self.controls.items():
            value = card.value(key)
            raw = drafts.get((card.id, key))
            blocker = QSignalBlocker(widget)
            if isinstance(widget, QCheckBox):
                widget.setCheckState(
                    Qt.CheckState.PartiallyChecked
                    if value is None
                    else Qt.CheckState.Checked
                    if value
                    else Qt.CheckState.Unchecked
                )
            elif isinstance(widget, QLineEdit):
                text = raw if raw is not None else field_text(value)
                widget.set_value(text, force=not self.edit_active(key))
            widget.setProperty("invalid", raw is not None)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            del blocker

    def _boolean(self, key, state):
        self.edited.emit(
            {
                key: None
                if state == Qt.CheckState.PartiallyChecked
                else state == Qt.CheckState.Checked
            }
        )
