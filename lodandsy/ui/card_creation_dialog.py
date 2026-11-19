from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
)

from lodandsy.domain.card_templates import CARD_TEMPLATES


class CardCreationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новая карточка")
        self.title_edit = QLineEdit(self)
        self.template = QComboBox(self)
        for template in CARD_TEMPLATES:
            self.template.addItem(template.title, template.id)
        layout = QFormLayout(self)
        layout.addRow("Название:", self.title_edit)
        layout.addRow("Шаблон:", self.template)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                  | QDialogButtonBox.StandardButton.Cancel, self)
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
        return dialog.title_edit.text().strip(), dialog.template.currentData(), accepted
