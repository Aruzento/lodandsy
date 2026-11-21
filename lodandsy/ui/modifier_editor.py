"""Bounded structured Item editor. Raw drafts use the shared FieldEdits contract."""

import json
from dataclasses import asdict
from uuid import uuid4

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

FIELDS = ("target", "operation", "operand", "group", "policy", "priority", "condition", "id")


class ModifierEditor(QWidget):
    raw_changed = Signal(str)
    commit_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        notice = QLabel(
            "Только явно активные предметы влияют на участника. "
            "Операции: set → multiply → add → minimum → maximum; "
            "совмещение: sum / max / unique. Условия без поддержки диагностируются."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.table = QTableWidget(0, len(FIELDS))
        self.table.setHorizontalHeaderLabels(
            ["Цель", "Операция", "Значение", "Группа", "Совмещение", "Приоритет", "Условие", "UUID"]
        )
        self.table.setColumnHidden(7, True)
        self.table.itemChanged.connect(lambda item: self.raw_changed.emit(self.raw()))
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        self.add = QPushButton("Добавить")
        self.remove = QPushButton("Удалить")
        self.apply = QPushButton("Применить")
        self.cancel = QPushButton("Отменить ввод")
        self.add.clicked.connect(self.add_modifier)
        self.remove.clicked.connect(self.remove_modifier)
        self.apply.clicked.connect(lambda: self.commit_requested.emit(self.raw()))
        self.cancel.clicked.connect(self.cancel_requested)
        for button in (self.add, self.remove, self.apply, self.cancel):
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def set_value(self, values, *, raw=None, active=False):
        if active:
            return
        data = [asdict(value) for value in values]
        if raw is not None:
            try:
                decoded = json.loads(raw)
                if isinstance(decoded, list):
                    data = decoded
            except ValueError:
                pass
        blocker = QSignalBlocker(self.table)
        self.table.setRowCount(len(data))
        for row, value in enumerate(data):
            for column, key in enumerate(FIELDS):
                self.table.setItem(row, column, QTableWidgetItem(str(value.get(key, ""))))
        del blocker

    def raw(self):
        rows = []
        for row in range(self.table.rowCount()):
            data = {
                key: self.table.item(row, col).text() if self.table.item(row, col) else ""
                for col, key in enumerate(FIELDS)
            }
            for key in ("operand", "priority"):
                try:
                    value = float(data[key]) if key == "operand" else int(data[key])
                    data[key] = int(value) if type(value) is float and value.is_integer() else value
                except ValueError:
                    pass
            rows.append(data)
        return json.dumps(rows, ensure_ascii=False)

    def add_modifier(self):
        if self.table.rowCount() >= 64:
            return
        values = json.loads(self.raw())
        values.append(
            dict(
                target="constitution",
                operation="add",
                operand=2,
                group="",
                policy="sum",
                priority=0,
                condition="",
                id=str(uuid4()),
            )
        )
        self.set_value((), raw=json.dumps(values))
        self.raw_changed.emit(self.raw())

    def remove_modifier(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self.raw_changed.emit(self.raw())
