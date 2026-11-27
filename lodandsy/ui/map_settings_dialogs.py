from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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


def measurement_picker(parent=None, mode="grid"):
    combo = QComboBox(parent)
    combo.setAccessibleName("Измерение расстояний")
    combo.addItem("D&D 5e 2014", "grid")
    combo.addItem("Геометрическое", "geometry")
    combo.setCurrentIndex(max(0, combo.findData(mode)))
    return combo


class MapGridDialog(QDialog):
    def __init__(self, grid, parent=None, *, measurement_mode="grid"):
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
        self.scale_known = QCheckBox("Масштаб в футах известен")
        self.scale_known.setChecked(grid.feet_per_cell is not None)
        self.feet = number(self, grid.feet_per_cell or 5, 0.01, 1e9)
        self.measurement_mode_combo = measurement_picker(self, measurement_mode)
        for label, widget in [
            ("", self.enabled),
            ("Клетка (px карты):", self.cell),
            ("Смещение X:", self.x),
            ("Смещение Y:", self.y),
            ("Непрозрачность (%):", self.opacity),
            ("Цвет (#RRGGBB):", self.color),
            ("", self.scale_known),
            ("Футов на клетку:", self.feet),
            ("Измерение расстояний:", self.measurement_mode_combo),
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
            self.feet.value() if self.scale_known.isChecked() else None,
        )


class MapPortalDialog(QDialog):
    def __init__(self, portal=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Портал")
        layout = QFormLayout(self)
        self.label = QLineEdit(portal.label if portal else "", self)
        self.label.setMaxLength(200)
        self.label.setPlaceholderText("Пусто — название карты назначения")
        self.hide_label = QCheckBox("Не показывать название на карте", self)
        self.hide_label.setChecked(portal.hide_label if portal else False)
        layout.addRow("Название:", self.label)
        layout.addRow(self.hide_label)
        dialog_buttons(self, layout)


def dialog_buttons(parent, layout):
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent
    )
    buttons.accepted.connect(parent.accept)
    buttons.rejected.connect(parent.reject)
    layout.addRow(buttons)
    return buttons
