"""Native project rules workspace, typed examples and explicit preview/apply."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableView,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lodandsy.domain.card_schema import FIELD_DEFINITIONS
from lodandsy.domain.formula import evaluate
from lodandsy.domain.rules_5e14 import DEFAULT_FORMULAS, FUNCTIONS, INPUT_NAMES, compile_rules
from lodandsy.ui.game_labels import choice_label, error_text, field_label, value_text
from lodandsy.ui.hit_history import HitHistoryEdit
from lodandsy.ui.theme import apply_role


def formula_group(key):
    if key in {"hp_max", "ac", "speed"}:
        return "Хиты и защита"
    if key in {"weapon_attack", "casting_modifier", "spell_attack", "spell_dc"}:
        return "Атаки и заклинания"
    if key in {"carrying_capacity", "carried_weight"}:
        return "Прочие расчёты"
    return "Характеристики и навыки"


class PreviewModel(QAbstractTableModel):
    def __init__(self, parent):
        super().__init__(parent)
        self.rows = ()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 4

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role in {Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole}:
            return self.rows[index.row()][index.column()]

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return ("Карточка / участник", "Показатель", "Было", "Будет")[section]

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = tuple(rows)
        self.endResetModel()


class RulesEditor(QWidget):
    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service, self.generation = service, service.core.generation
        self.rules_revision = service.rules.revision
        self.drafts = dict(service.rules.overrides)
        self.preview, self._target = None, None
        self.example_controls = {}
        self._example_types = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        self.warning = QLabel(
            "Предпросмотр не меняет мир. Применение может уменьшить текущие хиты "
            "до нового максимума. "
            "Сброс формулы не возвращает уже потерянные хиты."
        )
        self.warning.setWordWrap(True)
        outer.addWidget(self.warning)
        self.splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Найти правило…")
        self.search.setAccessibleName("Поиск правила по русскому названию")
        left_layout.addWidget(self.search)
        self.catalog = QTreeWidget()
        self.catalog.setHeaderHidden(True)
        self.catalog.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.catalog.setAccessibleName("Каталог правил")
        self.catalog.setMinimumWidth(112)
        left_layout.addWidget(self.catalog)
        self.splitter.addWidget(left)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.detail_scroll = scroll
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        detail = QVBoxLayout(content)
        detail.setContentsMargins(12, 0, 0, 0)
        detail.setAlignment(Qt.AlignmentFlag.AlignTop)
        detail.setSpacing(10)
        self.heading = QLabel()
        apply_role(self.heading, "group")
        self.heading.setWordWrap(True)
        detail.addWidget(self.heading)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setTextFormat(Qt.TextFormat.PlainText)
        detail.addWidget(self.description)
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("Изменить формулу · расширенный режим")
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        detail.addWidget(self.advanced_toggle)
        self.advanced = QWidget()
        advanced_layout = QVBoxLayout(self.advanced)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        self.expression = QPlainTextEdit()
        self.expression.setAccessibleName("Безопасная формула")
        self.expression.setMaximumHeight(110)
        advanced_layout.addWidget(self.expression)
        self.tokens = QComboBox()
        self.tokens.setAccessibleName("Вставить переменную или оператор")
        advanced_layout.addWidget(self.tokens)
        self.tokens.activated.connect(
            lambda index: self.expression.insertPlainText(self.tokens.itemData(index) or "")
        )
        hint = QLabel(
            "Разрешены числа, имена, + − * /, сравнения, if/else и чистые функции. "
            "Формула применяется только после проверки проекта."
        )
        hint.setWordWrap(True)
        advanced_layout.addWidget(hint)
        self.advanced.hide()
        self.advanced_toggle.toggled.connect(self.advanced.setVisible)
        self.advanced_toggle.toggled.connect(
            lambda checked: self.advanced_toggle.setArrowType(
                Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
            )
        )
        detail.addWidget(self.advanced)
        self.example_title = QLabel("Проверка на примере")
        detail.addWidget(self.example_title)
        self.example_widget = QWidget()
        self.example_form = QFormLayout(self.example_widget)
        self.example_form.setContentsMargins(0, 0, 0, 0)
        self.example_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        detail.addWidget(self.example_widget)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail.addWidget(self.status)
        self.preview_caption = QLabel("Изменения после применения")
        detail.addWidget(self.preview_caption)
        self.preview_model = PreviewModel(self)
        self.preview_table = QTableView()
        self.preview_table.setModel(self.preview_model)
        self.preview_table.setMinimumHeight(160)
        self.preview_table.setMaximumHeight(280)
        self.preview_table.setAccessibleName("Предпросмотр изменений участников")
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.preview_table.horizontalHeader().setMinimumSectionSize(35)
        self.preview_table.verticalHeader().hide()
        self.preview_table.hide()
        self.preview_caption.hide()
        detail.addWidget(self.preview_table)
        scroll.setWidget(content)
        self.splitter.addWidget(scroll)
        self.splitter.setSizes([230, 700])
        outer.addWidget(self.splitter, 1)
        buttons = QGridLayout()
        self.test, self.check, self.apply = (
            QPushButton(s) for s in ("Проверить пример", "Предпросмотр", "Применить")
        )
        self.reset, self.reset_all, self.reload = (
            QPushButton(s) for s in ("Сброс выбранной", "Сброс всех", "Загрузить сохранённые")
        )
        self.apply.setObjectName("primaryAction")
        self.apply.setEnabled(False)
        detail.insertWidget(detail.indexOf(self.status), self.test, 0, Qt.AlignmentFlag.AlignLeft)
        for col, button in enumerate((self.reset, self.reset_all, self.reload)):
            buttons.addWidget(button, 0, col)
        outer.addLayout(buttons)
        self.test.clicked.connect(self.test_example)
        self.check.clicked.connect(self.check_project)
        self.apply.clicked.connect(self.apply_project)
        self.reset.clicked.connect(self.reset_formula)
        self.reset_all.clicked.connect(self.reset_defaults)
        self.reload.clicked.connect(self.reload_saved)
        self.expression.textChanged.connect(self.capture)
        self.catalog.currentItemChanged.connect(self.load_formula)
        self.search.textChanged.connect(self.filter_catalog)
        self.items = {}
        general = QTreeWidgetItem(["Общие"])
        self.catalog.addTopLevelItem(general)
        groups = {}
        for key in sorted(DEFAULT_FORMULAS, key=field_label):
            group = formula_group(key)
            if group not in groups:
                groups[group] = QTreeWidgetItem([group])
                self.catalog.addTopLevelItem(groups[group])
            item = QTreeWidgetItem([field_label(key)])
            item.setData(0, Qt.ItemDataRole.UserRole, key)
            groups[group].addChild(item)
            self.items[key] = item
        self.catalog.expandAll()
        self.catalog.setCurrentItem(general)
        service.core.committed.connect(self._canonical_changed)

    def _canonical_changed(self):
        if self.preview is not None:
            self.preview = None
            self.apply.setEnabled(False)
            self.status.setText("Предпросмотр устарел: данные мира изменились. Повторите проверку.")

    @property
    def dirty(self):
        return self.drafts != dict(self.service.rules.overrides)

    def filter_catalog(self, text):
        words = text.casefold().split()
        for key, item in self.items.items():
            item.setHidden(not all(word in field_label(key).casefold() for word in words))
        for i in range(self.catalog.topLevelItemCount()):
            group = self.catalog.topLevelItem(i)
            if group.childCount():
                group.setHidden(all(group.child(j).isHidden() for j in range(group.childCount())))
        self.catalog.expandAll()

    def select_formula(self, key):
        self.catalog.setCurrentItem(self.items[key])

    def capture(self):
        if self._target:
            source = self.expression.toPlainText()
            if source == DEFAULT_FORMULAS[self._target]:
                self.drafts.pop(self._target, None)
            else:
                self.drafts[self._target] = source
        self.preview = None
        self.apply.setEnabled(False)
        self.preview_model.set_rows(())
        self.preview_table.hide()
        self.preview_caption.hide()

    def load_formula(self, *_args):
        self.status.clear()
        item = self.catalog.currentItem()
        key = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        self._target = None
        self.expression.setPlainText(self.drafts.get(key, DEFAULT_FORMULAS.get(key, "")))
        self._target = key
        self.heading.setText(field_label(key) if key else "D&D 5e 2014")
        self.advanced_toggle.setVisible(bool(key))
        self.advanced.setVisible(bool(key) and self.advanced_toggle.isChecked())
        self.example_widget.setVisible(bool(key))
        self.example_title.setVisible(bool(key))
        self.test.setEnabled(bool(key))
        self.reset.setEnabled(bool(key))
        if key:
            self.description.setText(
                (
                    "Стандартное правило. "
                    if key not in self.drafts
                    else "Изменённая формула проекта. "
                )
                + "Выход: "
                + field_label(key)
                + ". Входы задаются ниже; проверка примера не меняет мир."
                + (
                    " Формула КД задаёт основу и Ловкость; щит и модификаторы предметов "
                    "добавляются после неё. Ручной итог включает всё."
                    if key == "ac"
                    else ""
                )
            )
            self.tokens.clear()
            self.tokens.addItem("Вставить…", "")
            for name in sorted((INPUT_NAMES | DEFAULT_FORMULAS.keys()) - {key}, key=field_label):
                self.tokens.addItem(f"{field_label(name)} ({name})", name)
            for operator in (
                " + ",
                " - ",
                " * ",
                " / ",
                "floor(",
                "min(",
                "max(",
                " if ",
                " else ",
            ):
                self.tokens.addItem(operator, operator)
            self._build_inputs()
        else:
            self.description.setText(
                "Профиль: D&D 5e 2014, версия 1. Другие игровые системы пока не подключены. "
                "Выберите правило слева. Стандартные формулы остаются доступны после изменения."
            )

    def _build_inputs(self):
        try:
            expressions, _ = compile_rules(tuple(sorted(self.drafts.items())))
        except ValueError as error:
            self.status.setText(error_text(error))
            expressions, _ = compile_rules(())
        names = sorted(
            expressions[self._target].dependencies - {"armor_none", "armor_light", "armor_medium"},
            key=field_label,
        )
        try:
            existing = self._input_values() if self.example_controls else {}
        except ValueError:
            existing = {}
        while self.example_form.rowCount():
            self.example_form.removeRow(0)
        self.example_controls, self._example_types = {}, {}
        for name in names:
            key = name.removeprefix("base_")
            definition = FIELD_DEFINITIONS.get(key)
            default = existing.get(
                name,
                definition.default
                if definition
                else True
                if name in {"is_character", "is_single_class"}
                else "none"
                if key == "armor_type"
                else 10
                if key == "armor_base"
                else 0,
            )
            if name == "hp_gains":
                control = HitHistoryEdit()
                control.level = int(existing.get("level") or 1)
                control.set_value(", ".join(map(str, default or ())))
                control.commit_requested.connect(lambda raw, widget=control: widget.set_value(raw))
                kind = "sequence"
            elif (
                name in {"is_character", "is_single_class"}
                or key == "shield"
                or definition
                and definition.data_type == "bool"
            ):
                control = QCheckBox()
                control.setChecked(bool(default))
                kind = "bool"
            elif key == "armor_type":
                control = QComboBox()
                for value in ("none", "light", "medium", "heavy"):
                    control.addItem(choice_label(key, value), value)
                control.setCurrentIndex(control.findData(default))
                kind = "choice"
            elif definition and definition.choices:
                control = QComboBox()
                if definition.nullable:
                    control.addItem("Не задано", None)
                for value in definition.choices:
                    control.addItem(choice_label(key, value), value)
                control.setCurrentIndex(control.findData(default))
                kind = "choice"
            else:
                control = QLineEdit("" if default is None else str(default))
                control.setPlaceholderText("Не задано")
                kind = (
                    "text"
                    if definition and definition.data_type in {"text", "asset", "entity"}
                    else "number"
                )
                if kind == "number":
                    control.setValidator(QDoubleValidator(-1e9, 1e9, 6, control))
            control.setObjectName("example_" + name)
            control.setAccessibleName(field_label(name))
            self.example_controls[name] = control
            self._example_types[name] = kind
            self.example_form.addRow(field_label(name), control)
        history = self.example_controls.get("hp_gains")
        if history:
            history.button.pressed.connect(self._history_context)

    def _history_context(self):
        history = self.example_controls.get("hp_gains")
        if history:
            try:
                values = self._input_values()
            except ValueError as exc:
                self.status.setText(error_text(str(exc)))
                return
            history.level = values.get("level") or 1
            history.die = values.get("hit_die")

    def _input_values(self):
        values = {"armor_none": "none", "armor_light": "light", "armor_medium": "medium"}
        for key, control in self.example_controls.items():
            kind = self._example_types[key]
            if kind == "sequence":
                raw = control.raw
                values[key] = tuple(int(v.strip()) for v in raw.split(",") if v.strip())
            elif kind == "bool":
                values[key] = control.isChecked()
            elif kind == "choice":
                values[key] = control.currentData()
            elif kind == "number":
                raw = control.text().strip()
                if not raw:
                    values[key] = None
                else:
                    value = float(raw.replace(",", "."))
                    values[key] = int(value) if value.is_integer() else value
            else:
                values[key] = control.text()
        return values

    def test_example(self):
        if not self._target:
            return
        try:
            expressions, _ = compile_rules(tuple(sorted(self.drafts.items())))
            wanted = expressions[self._target].dependencies - {
                "armor_none",
                "armor_light",
                "armor_medium",
            }
            if wanted != self.example_controls.keys():
                self._build_inputs()
            inputs = self._input_values()
            result = evaluate(expressions[self._target], inputs.get, FUNCTIONS)
            self.status.setText("Результат: " + str(result))
        except (ValueError, TypeError) as error:
            self.status.setText("Проверка примера: " + error_text(error))

    def check_project(self):
        try:
            if self.generation != self.service.core.generation:
                raise ValueError("Проект изменился — откройте его правила заново")
            self.preview = self.service.preview_rules(
                tuple(self.drafts.items()), expected_revision=self.rules_revision
            )
            effects = self.service.preview_effects(self.preview)
            expressions, _ = compile_rules(tuple(sorted(self.drafts.items())))
            wanted = (
                expressions[self._target].dependencies
                - {"armor_none", "armor_light", "armor_medium"}
                if self._target
                else set()
            )
            if self._target and wanted != self.example_controls.keys():
                self._build_inputs()
            rows = [
                (card, field_label(key) + " · " + actor, value_text(old), value_text(new))
                for card, actor, key, old, new in effects
            ]
            for reference, old, new in self.preview[2]:
                actor = self.service.get_actor(reference)
                rows.append((actor.name, "Ограничение текущих хитов", str(old), str(new)))
            self.preview_model.set_rows(rows)
            self.preview_caption.show()
            self.preview_table.setVisible(bool(rows))
            if rows:
                QTimer.singleShot(0, self, self._reveal_preview)
            self.status.setText(
                f"Предпросмотр готов. Изменений: {len(effects)}. "
                f"Ограничений текущих хитов: {len(self.preview[2])}."
            )
            self.apply.setEnabled(True)
        except (ValueError, TypeError) as error:
            self.preview = None
            self.apply.setEnabled(False)
            self.preview_model.set_rows(())
            self.status.setText(error_text(error))

    def _reveal_preview(self):
        if self.preview is not None and self.generation == self.service.core.generation:
            self.detail_scroll.ensureWidgetVisible(self.preview_table, 0, 8)

    def apply_project(self):
        if self.preview is None:
            return
        try:
            self.service.apply_rules(self.preview)
            self.rules_revision = self.service.rules.revision
            self.drafts = dict(self.service.rules.overrides)
            self.preview = None
            self.apply.setEnabled(False)
            self.status.setText("Правила применены. Значения пересчитаны одной операцией.")
        except ValueError as error:
            self.status.setText(error_text(error))
            self.preview = None
            self.apply.setEnabled(False)

    def reset_formula(self):
        if self._target:
            self.expression.setPlainText(DEFAULT_FORMULAS[self._target])

    def reset_defaults(self):
        self.drafts.clear()
        self.load_formula()
        self.capture()

    def reload_saved(self):
        if (
            self.dirty
            and QMessageBox.question(
                self,
                "Отбросить ввод?",
                "Загрузить сохранённые формулы вместо локальных правок?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.rules_revision = self.service.rules.revision
        self.drafts = dict(self.service.rules.overrides)
        self.load_formula()
        self.capture()
        self.status.setText("Загружены сохранённые правила.")
