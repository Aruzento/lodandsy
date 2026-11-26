"""Native tool controls for the current project's Item catalogue."""

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.domain.currency import format_rate, parse_base_units
from lodandsy.domain.treasure import (
    MAX_LOOT_COUNT,
    MAX_SHOP_COUNT,
    SHOP_ALL,
    LootParameters,
    ShopParameters,
)


class CatalogTable(QTableWidget):
    def __init__(self, headers, open_item, *, pin=None):
        super().__init__(0, len(headers))
        self.open_item, self.pin = open_item, pin
        self.setHorizontalHeaderLabels(headers)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.verticalHeader().hide()
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.cellClicked.connect(self._activate)
        self.cellActivated.connect(self._activate)
        if pin is not None:
            self.itemChanged.connect(self._pin_changed)

    def set_rows(self, rows, locked=()):
        current = self.item(self.currentRow(), 0)
        active_key = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        scroll = self.verticalScrollBar().value()
        with QSignalBlocker(self):
            self.setRowCount(0)
            self.setRowCount(len(rows))
            for row, (key, values, available) in enumerate(rows):
                for column, text in enumerate(values):
                    cell = QTableWidgetItem(text)
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    cell.setToolTip(text)
                    if column == 0 and available:
                        font = cell.font()
                        font.setUnderline(True)
                        cell.setFont(font)
                        cell.setForeground(self.palette().link())
                        cell.setData(Qt.ItemDataRole.UserRole, key)
                    self.setItem(row, column, cell)
                if self.pin is not None:
                    cell = QTableWidgetItem()
                    cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                    cell.setCheckState(
                        Qt.CheckState.Checked if key in locked else Qt.CheckState.Unchecked
                    )
                    self.setItem(row, self.columnCount() - 1, cell)
                if key == active_key:
                    self.setCurrentCell(row, 0)
            self.verticalScrollBar().setValue(scroll)

    def _activate(self, row, column):
        if column == 0 and (key := self.item(row, column).data(Qt.ItemDataRole.UserRole)):
            self.open_item(key)

    def _pin_changed(self, cell):
        if cell.column() == self.columnCount() - 1:
            self.pin(cell.row(), cell.checkState() == Qt.CheckState.Checked)


def range_row(first, second, name):
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    first.setAccessibleName(f"{name}, минимум")
    second.setAccessibleName(f"{name}, максимум")
    layout.addWidget(first, 1)
    layout.addWidget(QLabel("—"))
    layout.addWidget(second, 1)
    return row


def count_range(minimum, maximum, limit):
    controls = QSpinBox(), QSpinBox()
    for control, initial in zip(controls, (minimum, maximum)):
        control.setRange(0, limit)
        control.setValue(initial)
    return controls


def money_range(values):
    controls = tuple(QLineEdit(format_rate(value)) for value in values)
    for control in controls:
        control.setMaxLength(24)
    return controls


def tool_notice():
    label = QLabel()
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.hide()
    return label


def set_notice(label, message):
    label.setText(message)
    label.setVisible(bool(message))


class LootWidget(QWidget):
    def __init__(self, settings, parameters, generate, copy, pin, open_item):
        super().__init__()
        self.generate, self.copy = generate, copy
        self.selected = tuple(parameters.categories)
        self.count = count_range(parameters.minimum, parameters.maximum, MAX_LOOT_COUNT)
        self.budget = money_range(parameters.budget)
        self.money = money_range(parameters.money or (0, 10 * settings.currency.base.rate_units))
        self.category = QToolButton()
        self.category.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.category.setAccessibleName("Категории добычи")
        self.category_menu = QMenu(self.category)
        self.category.setMenu(self.category_menu)
        self.include_money = QCheckBox("Добавить монеты")
        self.include_money.setChecked(parameters.money is not None)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.addRow("Категории", self.category)
        form.addRow("Количество предметов", range_row(*self.count, "Количество предметов"))
        form.addRow("Общая стоимость", range_row(*self.budget, "Общая стоимость"))
        form.addRow(self.include_money)
        self.money_limits = range_row(*self.money, "Стоимость монет")
        form.addRow("Стоимость монет", self.money_limits)
        self.include_money.toggled.connect(self._toggle_money)
        self.money_label = form.labelForField(self.money_limits)
        self._toggle_money(self.include_money.isChecked())

        self.results = CatalogTable(("Предмет", "Кол-во", "Стоимость", "Вес", "Закрепить"),
                                    open_item, pin=pin)
        self.results.setAccessibleName("Результат генерации добычи")
        self.coin_box = QPlainTextEdit()
        self.coin_box.setAccessibleName("Монеты в добыче")
        self.coin_box.setReadOnly(True)
        self.coin_box.setMaximumHeight(64)
        self.coin_box.hide()
        self.summary, self.error = tool_notice(), tool_notice()
        self.error.setObjectName("errorNotice")
        self.generate_button = QPushButton("Сгенерировать")
        self.generate_button.clicked.connect(self._generate)
        self.copy_button = QPushButton("Копировать в инвентарь")
        self.copy_button.clicked.connect(self.copy)
        self.copy_button.setEnabled(False)
        buttons = QHBoxLayout()
        buttons.addWidget(self.generate_button)
        buttons.addWidget(self.copy_button)
        buttons.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.addLayout(form)
        outer.addLayout(buttons)
        outer.addWidget(self.error)
        outer.addWidget(self.results, 1)
        outer.addWidget(self.coin_box)
        outer.addWidget(self.summary)
        self._category_options = None
        self.set_settings(settings)

    def _toggle_money(self, enabled):
        self.money_limits.setVisible(enabled)
        self.money_label.setVisible(enabled)

    def set_settings(self, settings):
        abbreviation = settings.currency.base.abbreviation
        for control in (*self.budget, *self.money):
            control.setToolTip(f"Базовый номинал ({abbreviation})")
            control.setPlaceholderText(abbreviation)
        options = (("Без категории", None), *((c.name, c.id) for c in settings.categories))
        if options != self._category_options:
            self._category_options = options
            self._update_categories()

    def _update_categories(self):
        self.category_menu.clear()
        self.category_menu.addAction("Все категории", lambda: self._set_category())
        self.category_menu.addSeparator()
        valid = {key for _, key in self._category_options}
        self.selected = tuple(key for key in self.selected if key in valid)
        for label, key in self._category_options:
            action = self.category_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(key in self.selected)
            action.triggered.connect(lambda checked, k=key: self._set_category(k, checked))
        caption = f"Выбрано: {len(self.selected)}" if self.selected else "Все категории"
        self.category.setText(caption)

    def _set_category(self, key=None, checked=None):
        if checked is None:
            self.selected = ()
        elif checked:
            self.selected = (*self.selected, key)
        else:
            self.selected = tuple(value for value in self.selected if value != key)
        self._update_categories()

    def read_parameters(self):
        return LootParameters(
            self.count[0].value(), self.count[1].value(),
            tuple(parse_base_units(value.text()) for value in self.budget),
            self.selected,
            tuple(parse_base_units(value.text()) for value in self.money)
            if self.include_money.isChecked() else None,
        )

    def _generate(self):
        try:
            self.generate(self.read_parameters())
        except ValueError as error:
            set_notice(self.error, str(error))
        else:
            set_notice(self.error, "")

    def render(self, rows, locks, status, coins, copyable):
        self.results.set_rows(rows, locks)
        self.generate_button.setText("Перегенерировать" if rows or coins else "Сгенерировать")
        set_notice(self.summary, status)
        self.coin_box.setPlainText(coins)
        self.coin_box.setVisible(bool(coins))
        self.copy_button.setEnabled(copyable)


class ShopWidget(QWidget):
    def __init__(self, settings, parameters, generate, open_item):
        super().__init__()
        self.generate = generate
        self.category = QComboBox()
        self.category.setAccessibleName("Категория ассортимента")
        self.count = count_range(parameters.minimum, parameters.maximum, MAX_SHOP_COUNT)
        for widget in self.count:
            widget.setMinimum(1)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.addRow("Категория", self.category)
        form.addRow("Уникальных позиций", range_row(*self.count, "Уникальных позиций"))
        self.generate_button = QPushButton("Обновить ассортимент")
        self.generate_button.clicked.connect(self._generate)
        self.error, self.summary = tool_notice(), tool_notice()
        self.error.setObjectName("errorNotice")
        self.results = CatalogTable(("Предмет", "Цена за ед.", "Вес"), open_item)
        self.results.setAccessibleName("Ассортимент магазина")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.addLayout(form)
        outer.addWidget(self.generate_button, alignment=Qt.AlignmentFlag.AlignLeft)
        outer.addWidget(self.error)
        outer.addWidget(self.results, 1)
        outer.addWidget(self.summary)
        self._category_options = None
        self.set_settings(settings)
        self.category.setCurrentIndex(max(0, self.category.findData(parameters.category)))

    def set_settings(self, settings):
        options = (("Все категории", SHOP_ALL), ("Без категории", None),
                   *((c.name, c.id) for c in settings.categories))
        if options != self._category_options:
            current = self.category.currentData() if self.category.count() else SHOP_ALL
            self._category_options = options
            self.category.clear()
            for label, key in options:
                self.category.addItem(label, key)
            self.category.setCurrentIndex(max(0, self.category.findData(current)))

    def read_parameters(self):
        return ShopParameters(self.count[0].value(), self.count[1].value(),
                              self.category.currentData())

    def _generate(self):
        try:
            self.generate(self.read_parameters())
        except ValueError as error:
            set_notice(self.error, str(error))
        else:
            set_notice(self.error, "")

    def render(self, rows, status):
        self.results.set_rows(rows)
        set_notice(self.summary, status)
