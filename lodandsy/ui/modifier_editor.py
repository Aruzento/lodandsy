"""Compact Item list and typed dialogs; drafts use the existing FieldEdits transport."""

import json
from dataclasses import asdict

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.domain.modifiers import Modifier
from lodandsy.domain.rules_5e14 import DEFAULT_FORMULAS
from lodandsy.ui.game_labels import CHOICES, error_text, field_label, signed


def modifier_summary(row):
    operand, op = row.get("operand", 0), row.get("operation", "add")
    amount = (
        signed(operand)
        if op == "add" and type(operand) in (int, float)
        else (CHOICES.get(op, "Неизвестная операция") + " " + str(operand))
    )
    policy = CHOICES.get(row.get("policy"), "Неизвестное совмещение")
    return f"{field_label(row.get('target', ''))} {amount} · {policy}"


class ModifierDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = dict(data)
        self.setWindowTitle("Модификатор предмета")
        self.resize(470, 400)
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Найти показатель…")
        self.search.setAccessibleName("Поиск цели модификатора")
        layout.addWidget(self.search)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.target = QComboBox()
        self.target.setAccessibleName("Целевая переменная")
        self.targets = sorted(DEFAULT_FORMULAS, key=field_label)
        self.search.textChanged.connect(self.filter_targets)
        self.filter_targets("")
        self.target.setCurrentIndex(self.target.findData(data.get("target")))
        form.addRow("Показатель", self.target)
        self.operation = QComboBox()
        for key in ("add", "set", "multiply", "minimum", "maximum"):
            self.operation.addItem(CHOICES[key], key)
        self.operation.setCurrentIndex(self.operation.findData(data.get("operation", "add")))
        form.addRow("Действие", self.operation)
        self.operand = QDoubleSpinBox()
        self.operand.setRange(-1e9, 1e9)
        self.operand.setDecimals(3)
        self.operand.setValue(
            data.get("operand", 0) if type(data.get("operand")) in (int, float) else 0
        )
        form.addRow("Значение", self.operand)
        self.policy = QComboBox()
        for key in ("sum", "max", "unique"):
            self.policy.addItem(CHOICES[key], key)
        self.policy.setCurrentIndex(self.policy.findData(data.get("policy", "sum")))
        form.addRow("Совмещение", self.policy)
        layout.addLayout(form)
        disclosure = QToolButton()
        disclosure.setText("Дополнительно: группа и приоритет")
        disclosure.setCheckable(True)
        disclosure.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        disclosure.setArrowType(Qt.ArrowType.RightArrow)
        layout.addWidget(disclosure)
        advanced = QWidget()
        advanced_form = QFormLayout(advanced)
        advanced_form.setContentsMargins(0, 0, 0, 0)
        self.group = QLineEdit(data.get("group", ""))
        self.group.setMaxLength(64)
        self.group.setPlaceholderText("Без общей группы")
        advanced_form.addRow("Группа", self.group)
        self.priority = QSpinBox()
        self.priority.setRange(-10000, 10000)
        self.priority.setValue(data.get("priority", 0))
        advanced_form.addRow("Приоритет", self.priority)
        self.condition = QLineEdit(data.get("condition", ""))
        self.condition.setMaxLength(256)
        advanced_form.addRow("Условие", self.condition)
        note = QLabel(
            "Условия ещё не поддерживаются. Оставьте поле пустым; активность задаётся в инвентаре."
        )
        note.setWordWrap(True)
        advanced_form.addRow(note)
        advanced.hide()
        disclosure.toggled.connect(advanced.setVisible)
        disclosure.toggled.connect(
            lambda checked: disclosure.setArrowType(
                Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
            )
        )
        layout.addWidget(advanced)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setObjectName("errorNotice")
        layout.addWidget(self.error)
        layout.addStretch()
        buttons = QDialogButtonBox()
        buttons.addButton("Готово", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("Отмена", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def filter_targets(self, text):
        current = self.target.currentData()
        self.target.clear()
        for key in self.targets:
            if text.casefold() in field_label(key).casefold():
                self.target.addItem(field_label(key), key)
        if self.target.findData(current) >= 0:
            self.target.setCurrentIndex(self.target.findData(current))

    def accept(self):
        try:
            if self.target.currentData() not in DEFAULT_FORMULAS:
                raise ValueError("Выберите показатель из каталога")
            if self.condition.text().strip():
                raise ValueError("Условие не поддерживается. Удалите его явно или отмените правку.")
            if not self.operand.hasAcceptableInput():
                raise ValueError("Введите конечное число")
            value = self.operand.value()
            self.data.update(
                target=self.target.currentData(),
                operation=self.operation.currentData(),
                operand=int(value) if value.is_integer() else value,
                group=self.group.text(),
                policy=self.policy.currentData(),
                priority=self.priority.value(),
                condition=self.condition.text(),
            )
            Modifier(**self.data)
        except (TypeError, ValueError) as error:
            self.error.setText(error_text(error))
            self.error.show()
            return
        super().accept()


class ModifierEditor(QWidget):
    raw_changed = Signal(str)
    commit_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self):
        super().__init__()
        self._rows, self._saved_ids = [], set()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        notice = QLabel(
            "Бонус действует у участника с активным предметом. Количество не умножает бонус."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.list = QListWidget()
        self.list.setAccessibleName("Модификаторы предмета")
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemDoubleClicked.connect(lambda item: self.edit_modifier())
        self.list.setMinimumHeight(110)
        self.list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.list)
        self.empty = QLabel("Модификаторов пока нет. Добавьте показатель и величину бонуса.")
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)
        self.error = QLabel()
        self.error.setObjectName("errorNotice")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        buttons = QGridLayout()
        self.add, self.edit, self.remove = (
            QPushButton(s) for s in ("Добавить…", "Изменить…", "Удалить")
        )
        self.apply, self.cancel = QPushButton("Применить"), QPushButton("Отменить ввод")
        for i, (button, callback) in enumerate(
            (
                (self.add, self.add_modifier),
                (self.edit, self.edit_modifier),
                (self.remove, self.remove_modifier),
                (self.apply, self.apply_changes),
                (self.cancel, self.cancel_requested.emit),
            )
        ):
            buttons.addWidget(button, i // 3, i % 3)
            button.clicked.connect(callback)
        self.list.currentRowChanged.connect(self._selection)
        layout.addLayout(buttons)
        self._selection(-1)

    def _selection(self, row):
        self.edit.setEnabled(row >= 0)
        self.remove.setEnabled(row >= 0)

    def set_value(self, values, *, raw=None, active=False):
        if active:
            return
        self._saved_ids = {value.id for value in values}
        data = [asdict(value) for value in values]
        self.error.clear()
        self.error.hide()
        if raw is not None:
            try:
                data = json.loads(raw)
                if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
                    raise ValueError()
            except ValueError, RecursionError:
                self.error.setText(
                    "Черновик не удалось прочесть. Отмените ввод для возврата к сохранённым данным."
                )
                self.error.show()
                return
        self._rows = data
        self.refresh_list()

    def refresh_list(self):
        selected = self.list.currentRow()
        blocker = QSignalBlocker(self.list)
        self.list.clear()
        for row in self._rows:
            text = modifier_summary(row)
            if row.get("target") not in DEFAULT_FORMULAS:
                text += " · Цель не поддерживается — исправьте явно"
            if row.get("condition"):
                text += " · Условие не поддерживается"
            self.list.addItem(text)
        self.list.setCurrentRow(min(selected, len(self._rows) - 1))
        del blocker
        self.empty.setVisible(not self._rows)
        self.list.setVisible(bool(self._rows))
        self.list.setMinimumHeight(40)
        self.list.setMaximumHeight(min(300, max(40, len(self._rows) * 42)))
        self._selection(self.list.currentRow())

    def raw(self):
        return json.dumps(self._rows, ensure_ascii=False)

    def _edit_row(self, data, index=None):
        dialog = ModifierDialog(data, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if index is None:
                self._rows.append(dialog.data)
            else:
                self._rows[index] = dialog.data
            self.refresh_list()
            self.raw_changed.emit(self.raw())

    def add_modifier(self):
        if len(self._rows) < 64:
            self._edit_row(asdict(Modifier("constitution", operand=2)))

    def edit_modifier(self):
        index = self.list.currentRow()
        if index >= 0:
            self._edit_row(self._rows[index], index)

    def remove_modifier(self):
        index = self.list.currentRow()
        if index >= 0:
            self._rows.pop(index)
            self.refresh_list()
            self.raw_changed.emit(self.raw())

    def apply_changes(self):
        deleted = self._saved_ids - {row.get("id") for row in self._rows}
        if (
            deleted
            and QMessageBox.question(
                self,
                "Удалить модификаторы?",
                f"Будет удалено модификаторов: {len(deleted)}.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.commit_requested.emit(self.raw())
