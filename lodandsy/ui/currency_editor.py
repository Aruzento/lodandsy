"""Native currency settings with a local draft and a single explicit save."""

from dataclasses import replace
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lodandsy.domain.currency import (
    CUSTOM,
    MAX_DENOMINATIONS,
    STANDARD,
    CurrencySystem,
    Denomination,
    format_rate,
    parse_rate,
)
from lodandsy.domain.item_categories import MAX_CUSTOM_CATEGORIES, STANDARD_CATEGORIES, ItemCategory
from lodandsy.ui.theme import TABLE_ROW, apply_role


class CurrencyEditor(QWidget):
    def __init__(self, settings, used_ids, save_settings, parent=None):
        super().__init__(parent)
        system = settings.currency
        self._save_settings = save_settings
        self._used_ids = frozenset(used_ids)
        self._initial = settings
        self._shown_kind = None
        self._base_id = system.base_id if system.kind == CUSTOM else str(uuid4())
        self._custom_rows = (
            self._display_rows(system)
            if system.kind == CUSTOM
            else ((self._base_id, "Базовая монета", "бм", "1"),)
        )
        self._ids = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.pages = QStackedWidget()
        currencies = QWidget()
        currency_layout = QVBoxLayout(currencies)
        currency_layout.setContentsMargins(0, 0, 0, 0)
        self.pages.addWidget(currencies)
        outer.addWidget(self.pages, 1)
        form = QFormLayout()
        self.system = QComboBox()
        self.system.addItem("D&D 5e 2014", STANDARD)
        self.system.addItem("Пользовательская", CUSTOM)
        self.system.setCurrentIndex(self.system.findData(system.kind))
        self.system.setEnabled(not self._used_ids)
        if self._used_ids:
            self.system.setToolTip("Система закреплена сохранёнными ценами и кошельками")
        form.addRow("Система валют", self.system)
        currency_layout.addLayout(form)

        self.table = QTableWidget(0, 3)
        self.table.setAccessibleName("Номиналы валюты")
        self.table.setHorizontalHeaderLabels(("Номинал", "Сокращение", "Курс к базе"))
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(TABLE_ROW)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        currency_layout.addWidget(self.table)

        actions = QHBoxLayout()
        self.add_button = QPushButton("Добавить номинал")
        self.remove_button = QPushButton("Удалить")
        apply_role(self.remove_button, "danger")
        actions.addWidget(self.add_button)
        actions.addWidget(self.remove_button)
        actions.addStretch(1)
        currency_layout.addLayout(actions)

        categories = QWidget()
        category_layout = QVBoxLayout(categories)
        category_layout.setContentsMargins(0, 0, 0, 0)
        self.categories = QListWidget()
        self.categories.setAccessibleName("Категории предметов")
        category_layout.addWidget(self.categories)
        self.add_category = QPushButton("Добавить категорию…")
        self.add_category.clicked.connect(self._add_category)
        category_layout.addWidget(self.add_category, alignment=Qt.AlignmentFlag.AlignLeft)
        for category in settings.categories:
            self._insert_category(category, custom=category not in STANDARD_CATEGORIES)
        self.pages.addWidget(categories)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        apply_role(self.message, "error")
        outer.addWidget(self.message)

        self.system.currentIndexChanged.connect(self._show_mode)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.add_button.clicked.connect(self._add)
        self.remove_button.clicked.connect(self._remove)
        self._show_mode()
        self._saved_draft = self._draft()

    def select_section(self, section):
        self.pages.setCurrentIndex(int(section == "categories"))

    def _category_draft(self):
        return tuple(
            (item.data(Qt.ItemDataRole.UserRole), item.text())
            for index in range(len(STANDARD_CATEGORIES), self.categories.count())
            if (item := self.categories.item(index)) is not None
        )

    def _draft(self):
        return self._shown_kind, tuple(self._rows()), self._category_draft()

    @property
    def dirty(self):
        return self._draft() != self._saved_draft

    @staticmethod
    def _display_rows(system):
        return tuple(
            (denom.id, denom.name, denom.abbreviation, format_rate(denom.rate_units))
            for denom in system.denominations
        )

    def _rows(self):
        for row, key in enumerate(self._ids):
            yield key, *(self.table.item(row, column).text() for column in range(3))

    def _show_mode(self):
        if self._shown_kind == CUSTOM:
            self._custom_rows = tuple(self._rows())
        self._shown_kind = self.system.currentData()
        self.table.setRowCount(0)
        self._ids.clear()
        rows = (
            self._custom_rows
            if self._shown_kind == CUSTOM
            else self._display_rows(CurrencySystem())
        )
        base = self._base_id if self._shown_kind == CUSTOM else CurrencySystem().base_id
        for key, *values in rows:
            self._insert_row(key, values, base)
        self.message.clear()
        self._update_buttons()

    def _insert_row(self, key, values, base):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._ids.append(key)
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if self._shown_kind == STANDARD or (column == 2 and key in {base, *self._used_ids}):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if key == base:
                item.setToolTip("Базовая единица · курс 1")
            elif key in self._used_ids:
                item.setToolTip("Номинал используется. Курс и удаление заблокированы.")
            self.table.setItem(row, column, item)

    def _update_buttons(self):
        custom = self._shown_kind == CUSTOM
        row = self.table.currentRow()
        key = self._ids[row] if 0 <= row < len(self._ids) else None
        self.add_button.setEnabled(custom and len(self._ids) < MAX_DENOMINATIONS)
        self.remove_button.setEnabled(
            custom and key is not None and key != self._base_id and key not in self._used_ids
        )

    def _add(self):
        self._insert_row(str(uuid4()), ("", "", "1"), self._base_id)
        row = self.table.rowCount() - 1
        self.table.setCurrentCell(row, 0)
        self.table.editItem(self.table.item(row, 0))
        self._update_buttons()

    def _remove(self):
        row = self.table.currentRow()
        self._ids.pop(row)
        self.table.removeRow(row)
        self._update_buttons()

    def _insert_category(self, category, *, custom):
        item = QListWidgetItem(category.name, self.categories)
        item.setData(Qt.ItemDataRole.UserRole, category.id)
        if custom:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.add_category.setEnabled(
            self.categories.count() < len(STANDARD_CATEGORIES) + MAX_CUSTOM_CATEGORIES
        )

    def _add_category(self):
        text, accepted = QInputDialog.getText(self, "Новая категория", "Название")
        if accepted:
            try:
                self._insert_category(ItemCategory(str(uuid4()), text), custom=True)
            except ValueError as error:
                self.message.setText(str(error))

    def save(self):
        try:
            candidate = CurrencySystem()
            if self._shown_kind == CUSTOM:
                denominations = tuple(
                    Denomination(key, name, abbreviation, parse_rate(rate))
                    for key, name, abbreviation, rate in self._rows()
                )
                candidate = CurrencySystem(CUSTOM, self._base_id, denominations)
            self._initial.currency.validate_change(candidate, self._used_ids)
            categories = tuple(ItemCategory(*entry) for entry in self._category_draft())
            self._save_settings(self._initial, candidate, categories)
        except ValueError as error:
            self.message.setText(str(error))
            return False
        self._initial = replace(self._initial, currency=candidate, custom_categories=categories)
        self._saved_draft = self._draft()
        self.message.clear()
        return True
