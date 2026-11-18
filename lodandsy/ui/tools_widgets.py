from PySide6.QtCore import QPersistentModelIndex, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from lodandsy.application.clipboard import copy_text
from lodandsy.domain.tools import roll_dice
from lodandsy.ui.icons import icon


class DiceWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Кубики · NdM±K"))
        self.expression = QLineEdit("2d6+3")
        self.expression.setAccessibleName("Выражение кубиков")
        layout.addWidget(self.expression)
        buttons = QHBoxLayout()
        self.roll = QPushButton("Бросить / повторить")
        self.copy = QPushButton("Копировать результат")
        self.copy.setEnabled(False)
        buttons.addWidget(self.roll)
        buttons.addWidget(self.copy)
        layout.addLayout(buttons)
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        self.result.setAccessibleName("Результат броска")
        layout.addWidget(self.result)
        self.roll.clicked.connect(self.throw)
        self.expression.returnPressed.connect(self.throw)
        self.copy.clicked.connect(lambda: copy_text(self.result.toPlainText()))

    def throw(self):
        try:
            self.result.setPlainText(roll_dice(self.expression.text()).text())
            self.copy.setEnabled(True)
        except ValueError as error:
            self.result.setPlainText(str(error))
            self.copy.setEnabled(False)


class LiveTextDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        persistent = QPersistentModelIndex(index)
        editor.textEdited.connect(lambda text: persistent.model().setData(persistent, text)
                                  if persistent.isValid() else None)
        return editor


class RandomTableWidget(QWidget):
    rows_changed = Signal(tuple)
    rename_requested = Signal()
    delete_requested = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        actions = QToolBar(self)
        actions.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.add = QAction(icon("plus"), "Строка", self)
        self.remove = QAction(icon("delete"), "Убрать строку", self)
        self.up = QAction(icon("up"), "Выше", self)
        self.down = QAction(icon("down"), "Ниже", self)
        rename = QAction(icon("rename"), "Название", self)
        delete = QAction(icon("delete"), "Удалить таблицу", self)
        actions.addActions([self.add, self.remove, self.up, self.down, rename, delete])
        layout.addWidget(actions)
        layout.addWidget(QLabel("Двойной щелчок — редактировать. "
                               "Пустые строки не участвуют в выборе."))
        self.table = QTableWidget(0, 1)
        self.table.setHorizontalHeaderLabels(["Вариант"])
        self.table.setItemDelegate(LiveTextDelegate(self.table))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAccessibleName("Строки случайной таблицы")
        layout.addWidget(self.table)
        roll = QPushButton("Выбрать случайную строку")
        self.copy = QPushButton("Копировать результат")
        self.copy.setEnabled(False)
        bottom = QHBoxLayout()
        bottom.addWidget(roll)
        bottom.addWidget(self.copy)
        layout.addLayout(bottom)
        self.result = QLabel()
        self.result.setTextFormat(Qt.TextFormat.PlainText)
        self.result.setWordWrap(True)
        layout.addWidget(self.result)
        self.roll_requested = roll
        self.table.itemChanged.connect(self._changed)
        self.add.triggered.connect(self._add)
        self.remove.triggered.connect(self._remove)
        self.up.triggered.connect(lambda: self._move(-1))
        self.down.triggered.connect(lambda: self._move(1))
        rename.triggered.connect(self.rename_requested)
        delete.triggered.connect(self.delete_requested)
        self.copy.clicked.connect(lambda: copy_text(self.result.text()))
        self.add.setShortcut(QKeySequence("Ctrl+Return"))

    def rows(self):
        return tuple(self.table.item(i, 0).text() if self.table.item(i, 0) else ""
                     for i in range(self.table.rowCount()))

    def set_rows(self, rows):
        if self.rows() == rows:
            return
        selected = self.table.currentRow()
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.table.setItem(i, 0, QTableWidgetItem(row))
            if rows:
                self.table.setCurrentCell(max(0, min(selected, len(rows) - 1)), 0)
        finally:
            self.table.blockSignals(False)

    def _changed(self, *_args):
        self.rows_changed.emit(self.rows())

    def _add(self):
        self.set_rows((*self.rows(), ""))
        self.table.setCurrentCell(self.table.rowCount() - 1, 0)
        self.table.editItem(self.table.currentItem())
        self._changed()

    def _remove(self):
        index = self.table.currentRow()
        if index >= 0:
            self.table.removeRow(index)
            self._changed()

    def _move(self, direction):
        rows = list(self.rows())
        index, target = self.table.currentRow(), self.table.currentRow() + direction
        if 0 <= index < len(rows) and 0 <= target < len(rows):
            rows[index], rows[target] = rows[target], rows[index]
            self.set_rows(tuple(rows))
            self.table.setCurrentCell(target, 0)
            self._changed()
