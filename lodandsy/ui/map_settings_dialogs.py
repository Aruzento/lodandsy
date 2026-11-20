from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
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
        self.color = QLineEdit(grid.color)
        for label, widget in [
            ("", self.enabled),
            ("Клетка (px карты):", self.cell),
            ("Смещение X:", self.x),
            ("Смещение Y:", self.y),
            ("Непрозрачность (%):", self.opacity),
            ("Цвет (#RRGGBB):", self.color),
        ]:
            layout.addRow(label, widget)
        self.buttons = dialog_buttons(self, layout)
        self.color.textChanged.connect(self._validate)

    def _validate(self):
        try:
            self.grid()
            valid = True
        except ValueError:
            valid = False
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid)

    def grid(self):
        return MapGrid(
            self.enabled.isChecked(),
            self.cell.value(),
            self.x.value(),
            self.y.value(),
            self.opacity.value() / 100,
            self.color.text(),
        )


def dialog_buttons(parent, layout):
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent
    )
    buttons.accepted.connect(parent.accept)
    buttons.rejected.connect(parent.reject)
    layout.addRow(buttons)
    return buttons
