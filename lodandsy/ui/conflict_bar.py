from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QBoxLayout, QComboBox, QLabel, QPushButton, QVBoxLayout, QWidget


class ConflictBar(QWidget):
    resolve_requested = Signal(object, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        self.fields = QComboBox()
        self.fields.setAccessibleName("Конфликтный ввод")
        layout.addWidget(self.fields)
        self.actions = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        for label, mine in [("Использовать сохранённое", False), ("Применить мой вариант", True)]:
            button = QPushButton(label)
            button.clicked.connect(
                lambda checked=False, value=mine: self.resolve_requested.emit(
                    self.fields.currentData(), value
                )
            )
            self.actions.addWidget(button)
        layout.addLayout(self.actions)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.details)
        self.fields.currentIndexChanged.connect(self._details)
        self._rows = {}
        self.hide()

    def resizeEvent(self, event):
        self.actions.setDirection(
            QBoxLayout.Direction.TopToBottom
            if self.width() < 520
            else QBoxLayout.Direction.LeftToRight
        )
        super().resizeEvent(event)

    def set_conflicts(self, rows):
        current = self.fields.currentData()
        self._rows = {key: (raw, saved) for key, label, raw, saved in rows}
        labels = [(key, label) for key, label, raw, saved in rows]
        existing = [
            (self.fields.itemData(i), self.fields.itemText(i)) for i in range(self.fields.count())
        ]
        if existing != labels:
            self.fields.clear()
            for key, label in labels:
                self.fields.addItem(label, key)
            for i in range(self.fields.count()):
                if self.fields.itemData(i) == current:
                    self.fields.setCurrentIndex(i)
                    break
        self._details()
        self.setVisible(bool(rows))

    def _details(self):
        raw, saved = self._rows.get(self.fields.currentData(), ("", ""))
        self.details.setText(
            f"Конфликт · сохранённое: {str(saved)[:240]}\nМой вариант: {str(raw)[:240]}"
        )
