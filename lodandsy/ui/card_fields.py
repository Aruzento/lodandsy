"""Shared typed field controls; emits edits, never owns canonical world values."""

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QCheckBox, QFormLayout, QLineEdit, QWidget

from lodandsy.domain.card_schema import field_definition, parse_field


def field_text(value):
    return "" if value is None else ", ".join(value) if isinstance(value, tuple) else str(value)


class CardFieldsForm(QWidget):
    edited = Signal(object)
    draft_changed = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.controls = {}
        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setSpacing(8)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.keys = ()

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
                    widget = QLineEdit()
                    widget.setMaxLength(
                        definition.max_length if definition.data_type == "text" else 2048
                    )
                    widget.setPlaceholderText("—")
                    widget.textEdited.connect(lambda text, k=key: self._edit(k, text))
                    widget.editingFinished.connect(
                        lambda k=key: self._edit(k, self.controls[k].text())
                    )
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
                keep = False
                if widget.hasFocus() and raw is None:
                    try:
                        keep = parse_field(key, widget.text()) == value
                    except ValueError:
                        pass
                if not keep and widget.text() != text:
                    widget.setText(text)
            widget.setProperty("invalid", raw is not None)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            del blocker

    def _edit(self, key, text):
        try:
            value = parse_field(key, text)
            self.edited.emit({key: value})
        except ValueError:
            self.draft_changed.emit(key, text)

    def _boolean(self, key, state):
        self.edited.emit(
            {
                key: None
                if state == Qt.CheckState.PartiallyChecked
                else state == Qt.CheckState.Checked
            }
        )
