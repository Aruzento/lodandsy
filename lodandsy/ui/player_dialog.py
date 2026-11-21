from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)


class PlayerDialog(QDialog):
    def __init__(self, card, enabled, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Постоянный игрок" if enabled else "Независимые размещения")
        layout = QVBoxLayout(self)
        message = QLabel(
            "Будущие размещения используют выбранного участника. "
            "Существующие участники, инвентари и связи сохранятся."
            if enabled
            else "Будущие размещения и копии станут независимыми. "
            "Существующие связи и состояние сохранятся."
        )
        message.setWordWrap(True)
        layout.addWidget(message)
        self.choice = QComboBox()
        for actor in card.actors:
            self.choice.addItem(actor.name + " · " + actor.id[:8], actor.id)
        self.choice.addItem("Создать нового участника", None)
        if card.default_actor_id:
            self.choice.setCurrentIndex(self.choice.findData(card.default_actor_id))
        self.choice.setVisible(enabled)
        layout.addWidget(self.choice)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
