from dataclasses import replace
from uuid import uuid4

from PySide6.QtCore import QSignalBlocker, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.application.clipboard import copy_text
from lodandsy.domain.dice_document import FACES, DiceConfig, DicePreset, roll_dice
from lodandsy.ui.icons import icon


class DiceWidget(QWidget):
    document_changed = Signal(object)

    def __init__(self, document, runtime=None):
        super().__init__()
        self.document = document
        self.runtime = runtime if runtime is not None else {}
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.presets = QComboBox()
        self.presets.setAccessibleName("Заготовка броска")
        row.addWidget(self.presets, 1)
        for text, callback in [
            ("Создать", self.add_preset),
            ("Название", self.rename_preset),
            ("Дублировать", self.duplicate_preset),
            ("Удалить", self.delete_preset),
        ]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        grid = QGridLayout()
        self.counts = {}
        for column, faces in enumerate(FACES):
            label = QToolButton()
            label.setText(f"d{faces}")
            label.setIcon(icon(f"d{faces}", 40))
            label.setIconSize(QSize(40, 40))
            label.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            label.setToolTip(f"Добавить один d{faces}")
            label.clicked.connect(
                lambda _checked=False, f=faces: self.counts[f].setValue(self.counts[f].value() + 1)
            )
            grid.addWidget(label, 0, column)
            box = QSpinBox()
            box.setRange(0, 1000)
            box.setAccessibleName(f"Количество d{faces}")
            box.valueChanged.connect(self._edited)
            self.counts[faces] = box
            grid.addWidget(box, 1, column)
        layout.addLayout(grid)
        row = QHBoxLayout()
        row.addWidget(QLabel("Модификатор:"))
        self.modifier = QSpinBox()
        self.modifier.setRange(-1_000_000_000, 1_000_000_000)
        self.modifier.valueChanged.connect(self._edited)
        row.addWidget(self.modifier)
        clear = QPushButton("Очистить количества")
        clear.clicked.connect(self.clear_counts)
        row.addWidget(clear)
        layout.addLayout(row)
        self.formula = QLabel()
        self.formula.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.formula)
        row = QHBoxLayout()
        self.roll = QPushButton("Бросить / повторить")
        self.copy = QPushButton("Копировать результат")
        self.copy.setEnabled(False)
        row.addWidget(self.roll)
        row.addWidget(self.copy)
        layout.addLayout(row)
        self.total = QLabel()
        if "total" in self.runtime:
            self.total.setText(str(self.runtime["total"]))
        self.total.setStyleSheet("font-size:28px; color:#ceb075")
        layout.addWidget(self.total)
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        self.result.setAccessibleName("Результаты и история бросков текущей сессии")
        layout.addWidget(self.result, 1)
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setStyleSheet("color:#f19a9a")
        layout.addWidget(self.error)
        self.roll.clicked.connect(self.throw)
        self.copy.clicked.connect(lambda: copy_text(self.runtime.get("last", "")))
        self.presets.currentIndexChanged.connect(self._selected)
        self._refresh()
        self.result.setPlainText("\n\n".join(reversed(self.runtime.get("history", []))))
        self.copy.setEnabled(bool(self.runtime.get("last")))

    def current_preset(self):
        key = self.presets.currentData()
        return next((p for p in self.document.presets if p.id == key), None)

    def select_preset(self, key):
        index = self.presets.findData(key)
        if index >= 0:
            self.presets.setCurrentIndex(index)

    def set_document(self, document):
        if document != self.document:
            self.document = document
            self._refresh()

    def _refresh(self):
        key = self.runtime.get("selected", self.presets.currentData())
        blocker = QSignalBlocker(self.presets)
        self.presets.clear()
        for preset in self.document.presets:
            self.presets.addItem(preset.name, preset.id)
        self.presets.setCurrentIndex(max(0, self.presets.findData(key)))
        del blocker
        self._selected()

    def _selected(self):
        preset = self.current_preset()
        self.runtime["selected"] = preset.id if preset else None
        config = preset.config if preset else DiceConfig((0,) * 7)
        for faces, count in zip(FACES, config.counts):
            box = self.counts[faces]
            blocker = QSignalBlocker(box)
            box.setValue(count)
            box.setEnabled(preset is not None)
            del blocker
        blocker = QSignalBlocker(self.modifier)
        self.modifier.setValue(config.modifier)
        del blocker
        self.modifier.setEnabled(preset is not None)
        self.roll.setEnabled(preset is not None)
        self.formula.setText(config.expression())

    def _publish(self, presets):
        document = replace(self.document, presets=presets)
        if document != self.document:
            self.document = document
            self.document_changed.emit(document)
        self._refresh()

    def _edited(self):
        preset = self.current_preset()
        if preset is None:
            return
        try:
            config = DiceConfig(tuple(self.counts[f].value() for f in FACES), self.modifier.value())
            self.error.clear()
        except ValueError as error:
            self._selected()  # Reject the excessive change; saved configuration stays valid.
            self.error.setText(str(error))
            return
        self._publish(
            tuple(
                replace(p, config=config) if p.id == preset.id else p for p in self.document.presets
            )
        )

    def clear_counts(self):
        preset = self.current_preset()
        if preset:
            self._publish(
                tuple(
                    replace(p, config=DiceConfig((0,) * 7, 0)) if p.id == preset.id else p
                    for p in self.document.presets
                )
            )

    def add_preset(self):
        name, ok = QInputDialog.getText(self, "Новая заготовка", "Название:")
        if ok and name.strip():
            self._safe_publish(lambda: (*self.document.presets, DicePreset(name)))
            self.presets.setCurrentIndex(self.presets.count() - 1)

    def rename_preset(self):
        preset = self.current_preset()
        if preset:
            name, ok = QInputDialog.getText(self, "Заготовка", "Название:", text=preset.name)
            if ok and name.strip():
                self._safe_publish(
                    lambda: tuple(
                        replace(p, name=name) if p.id == preset.id else p
                        for p in self.document.presets
                    )
                )

    def duplicate_preset(self):
        preset = self.current_preset()
        if preset:
            self._safe_publish(
                lambda: (
                    *self.document.presets,
                    replace(preset, id=str(uuid4()), name=preset.name[:190] + " (копия)"),
                )
            )
            self.presets.setCurrentIndex(self.presets.count() - 1)

    def delete_preset(self):
        preset = self.current_preset()
        if (
            preset
            and QMessageBox.question(self, "Заготовка", "Удалить заготовку?")
            == QMessageBox.StandardButton.Yes
        ):
            self._publish(tuple(p for p in self.document.presets if p.id != preset.id))

    def _safe_publish(self, presets):
        try:
            self._publish(presets())
        except ValueError as error:
            self.error.setText(str(error))

    def throw(self):
        preset = self.current_preset()
        try:
            if preset is None:
                raise ValueError("Создайте заготовку")
            result = roll_dice(preset.config)
            text = result.text()
            self.runtime["last"] = text
            self.runtime["total"] = result.total
            history = self.runtime.setdefault("history", [])
            history.append(text)
            del history[:-50]
            self.total.setText(str(result.total))
            self.result.setPlainText("\n\n".join(reversed(history)))
            self.copy.setEnabled(True)
            self.error.clear()
        except ValueError as error:
            self.error.setText(str(error))
