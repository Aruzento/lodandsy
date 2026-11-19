from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
)

from lodandsy.domain.map_document import MapGrid


def number(parent, value, minimum=0, maximum=1_000_000):
    box = QDoubleSpinBox(parent)
    box.setRange(minimum, maximum)
    box.setDecimals(2)
    box.setValue(value)
    return box


class MapGridDialog(QDialog):
    def __init__(self, grid, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Сетка карты")
        layout = QFormLayout(self)
        self.enabled = QCheckBox("Показывать квадратную сетку", self)
        self.enabled.setChecked(grid.enabled)
        self.cell = number(self, grid.cell_size, 1)
        self.x = number(self, grid.offset_x, -1e9, 1e9)
        self.y = number(self, grid.offset_y, -1e9, 1e9)
        self.opacity = number(self, grid.opacity * 100, 0, 100)
        self.snap = QCheckBox("Прилипание к центрам клеток", self)
        self.snap.setChecked(grid.snap)
        self.snap.setToolTip("Применяется при перемещении; скрытая сетка тоже поддерживает snap")
        for label, widget in [("", self.enabled), ("Клетка (px карты):", self.cell),
                               ("Смещение X:", self.x), ("Смещение Y:", self.y),
                               ("Непрозрачность (%):", self.opacity), ("", self.snap)]:
            layout.addRow(label, widget)
        self.buttons = dialog_buttons(self, layout)

    def grid(self):
        return MapGrid(self.enabled.isChecked(), self.cell.value(), self.x.value(),
                       self.y.value(), self.opacity.value() / 100, self.snap.isChecked())


def dialog_buttons(parent, layout):
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel, parent)
    buttons.accepted.connect(parent.accept)
    buttons.rejected.connect(parent.reject)
    layout.addRow(buttons)
    return buttons


class TokenPropertiesDialog(QDialog):
    def __init__(self, token, cards, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Свойства токена")
        layout = QFormLayout(self)
        self.title = QLineEdit(token.title, self)
        self.width = number(self, token.width, 1)
        self.height = number(self, token.height, 1)
        self.z = QSpinBox(self)
        self.z.setRange(0, 10000)
        self.z.setValue(token.z)
        self.card = QComboBox(self)
        self.card.addItem("Без связи", None)
        for card in cards:
            self.card.addItem(f"{card.title} · {card.id}", card.id)
        if token.card_id and self.card.findData(token.card_id) == -1:
            self.card.addItem(f"Разорванная ссылка · {token.card_id}", token.card_id)
        self.card.setCurrentIndex(max(0, self.card.findData(token.card_id)))
        for label, widget in [("Название:", self.title), ("Ширина (px карты):", self.width),
                               ("Высота (px карты):", self.height), ("Порядок:", self.z),
                               ("Карточка:", self.card)]:
            layout.addRow(label, widget)
        self.buttons = dialog_buttons(self, layout)
        self.ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.title.textChanged.connect(lambda text: self.ok.setEnabled(bool(text.strip())))

    def changes(self):
        return {"title": self.title.text().strip(), "width": self.width.value(),
                "height": self.height.value(), "z": self.z.value(),
                "card_id": self.card.currentData()}
