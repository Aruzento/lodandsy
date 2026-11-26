"""Native tool controls for the current project's Item catalogue."""

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
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
from lodandsy.ui.icons import icon
from lodandsy.ui.theme import TABLE_ROW, apply_role


class CatalogTable(QTableWidget):
    def __init__(self, headers, open_item, *, pin=None):
        super().__init__(0, len(headers))
        self.open_item, self.pin = open_item, pin
        self.setHorizontalHeaderLabels(headers)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setMinimumHeight(112)
        self.verticalHeader().setDefaultSectionSize(TABLE_ROW)
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
                    elif column:
                        cell.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                              | Qt.AlignmentFlag.AlignVCenter)
                    self.setItem(row, column, cell)
                if self.pin is not None:
                    cell = QTableWidgetItem()
                    cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                                  | Qt.ItemFlag.ItemIsSelectable)
                    cell.setToolTip("Закрепить эту позицию")
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


def range_row(first, second, name, unit=None):
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    first.setAccessibleName(f"{name}, минимум")
    second.setAccessibleName(f"{name}, максимум")
    layout.addWidget(first, 1)
    layout.addWidget(QLabel("—"))
    layout.addWidget(second, 1)
    if unit is not None:
        apply_role(unit, "group")
        layout.addWidget(unit)
    return row


def count_range(minimum, maximum, limit):
    controls = QSpinBox(), QSpinBox()
    for control, initial in zip(controls, (minimum, maximum)):
        control.setRange(0, limit)
        control.setValue(initial)
        control.setMinimumWidth(44)
    return controls


def money_range(values):
    controls = tuple(QLineEdit(format_rate(value)) for value in values)
    for control in controls:
        control.setMaxLength(24)
        control.setMinimumWidth(44)
        control.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
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


def parameter_panel(form, actions):
    panel = QWidget()
    apply_role(panel, "parameterPanel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(8)
    form.setVerticalSpacing(4)
    layout.addLayout(form)
    layout.addLayout(actions)
    return panel


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
        form.addRow("Предметов", range_row(*self.count, "Количество предметов"))
        self.budget_unit, self.money_unit = QLabel(), QLabel()
        form.addRow("Общий бюджет", range_row(*self.budget, "Общая стоимость", self.budget_unit))
        form.addRow(self.include_money)
        self.money_limits = range_row(*self.money, "Стоимость монет", self.money_unit)
        form.addRow("Стоимость монет", self.money_limits)
        self.include_money.toggled.connect(self._toggle_money)
        self.money_label = form.labelForField(self.money_limits)
        self._toggle_money(self.include_money.isChecked())

        self.results = CatalogTable(("Предмет", "Кол-во", "Стоимость", "Вес", "Фикс."),
                                    open_item, pin=pin)
        self.results.setAccessibleName("Результат генерации добычи")
        self.coin_box = tool_notice()
        self.coin_box.setAccessibleName("Монеты в добыче")
        self.summary, self.error = tool_notice(), tool_notice()
        apply_role(self.summary, "total")
        apply_role(self.error, "error")
        self.generate_button = QPushButton("Сгенерировать")
        apply_role(self.generate_button, "primary")
        self.generate_button.clicked.connect(self._generate)
        self.copy_button = QPushButton(icon("copy"), "Копировать")
        self.copy_button.setAccessibleName("Копировать результат в инвентарь")
        self.copy_button.setToolTip(self.copy_button.accessibleName())
        self.copy_button.clicked.connect(self.copy)
        self.copy_button.setEnabled(False)
        buttons = self.actions = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        buttons.addWidget(self.generate_button)
        buttons.addWidget(self.copy_button)
        buttons.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.addWidget(parameter_panel(form, buttons))
        outer.addWidget(self.error)
        outer.addWidget(self.results, 1)
        outer.addWidget(self.coin_box)
        outer.addWidget(self.summary)
        self._category_options = None
        self.set_settings(settings)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.actions.setDirection(
            QBoxLayout.Direction.TopToBottom if self.width() < 300
            else QBoxLayout.Direction.LeftToRight
        )

    def _toggle_money(self, enabled):
        self.money_limits.setVisible(enabled)
        self.money_label.setVisible(enabled)

    def set_settings(self, settings):
        abbreviation = settings.currency.base.abbreviation
        self.budget_unit.setText(abbreviation)
        self.money_unit.setText(abbreviation)
        for control in (*self.budget, *self.money):
            control.setToolTip(f"Базовый номинал ({abbreviation})")
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
        set_notice(self.summary, status or "Задайте диапазоны и сгенерируйте добычу.")
        set_notice(self.coin_box, coins)
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
        apply_role(self.generate_button, "primary")
        self.generate_button.clicked.connect(self._generate)
        self.error, self.summary = tool_notice(), tool_notice()
        apply_role(self.error, "error")
        apply_role(self.summary, "total")
        self.results = CatalogTable(("Предмет", "Цена за ед.", "Вес"), open_item)
        self.results.setAccessibleName("Ассортимент магазина")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 8)
        actions = QHBoxLayout()
        actions.addWidget(self.generate_button)
        actions.addStretch(1)
        outer.addWidget(parameter_panel(form, actions))
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
        set_notice(self.summary, status or "Выберите категорию и обновите ассортимент.")
