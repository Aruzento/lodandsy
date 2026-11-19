from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
)

from lodandsy.domain.card_schema import CARD_TYPES
from lodandsy.domain.card_templates import CARD_TEMPLATES


class CardCreationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новая карточка")
        self.title_edit = QLineEdit(self)
        self.template = QComboBox(self)
        for template in CARD_TEMPLATES:
            self.template.addItem(template.title, template.id)
        self.card_type = QComboBox(self)
        for definition in CARD_TYPES.values():
            self.card_type.addItem(definition.title, definition.id)
        layout = QFormLayout(self)
        layout.addRow("Название:", self.title_edit)
        layout.addRow("Тип:", self.card_type)
        layout.addRow("Шаблон:", self.template)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setEnabled(False)
        self.title_edit.textChanged.connect(lambda text: self.ok.setEnabled(bool(text.strip())))
        layout.addRow(buttons)

    @classmethod
    def get_card(cls, parent):
        dialog = cls(parent)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        return (
            dialog.title_edit.text().strip(),
            dialog.template.currentData(),
            dialog.card_type.currentData(),
            accepted,
        )
