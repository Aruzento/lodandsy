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


class TokenPropertiesDialog(QDialog):
    def __init__(self, token, presentation, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Свойства размещения · " + presentation.label)
        layout = QFormLayout(self)
        self.title = QLineEdit(token.label_override or "", self)
        self.title.setPlaceholderText("Из карточки: " + presentation.label)
        self.width, self.height = QSpinBox(self), QSpinBox(self)
        for box, value in [(self.width, token.cells_w), (self.height, token.cells_h)]:
            box.setRange(0, 100)
            box.setSpecialValueText("Из карточки")
            box.setValue(value or 0)
        self.kind = QComboBox(self)
        for label, value in [
            ("Из карточки", None),
            ("Персонаж (круг)", "character"),
            ("Предмет", "item"),
        ]:
            self.kind.addItem(label, value)
        self.kind.setCurrentIndex(self.kind.findData(token.kind_override))
        self.z = QSpinBox(self)
        self.z.setRange(0, 10000)
        self.z.setValue(token.z)
        for label, widget in [
            ("Своя подпись:", self.title),
            ("Свой вид:", self.kind),
            ("Ширина (клетки):", self.width),
            ("Высота (клетки):", self.height),
            ("Порядок:", self.z),
        ]:
            layout.addRow(label, widget)
        self.buttons = dialog_buttons(self, layout)

    def changes(self):
        return dict(
            label_override=self.title.text().strip() or None,
            cells_w=self.width.value() or None,
            cells_h=self.height.value() or None,
            kind_override=self.kind.currentData(),
            z=self.z.value(),
        )
