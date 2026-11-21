"""Project formula drafts, bounded examples and explicit preview/apply."""

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from lodandsy.domain.formula import CalculationError, evaluate
from lodandsy.domain.rules_5e14 import DEFAULT_FORMULAS, FUNCTIONS, compile_rules


class RulesEditor(QDialog):
    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service, self.generation = service, service.core.generation
        self.rules_revision = service.rules.revision
        self.drafts = dict(service.rules.overrides)
        self.preview = None
        self._target = None
        self.setWindowTitle("Правила проекта · D&D 5e 2014")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(760, 650)
        layout = QVBoxLayout(self)
        notice = QLabel(
            "Формулы действуют на весь проект. Проверка не меняет данные. "
            "Применение может ограничить текущее HP при снижении максимума; "
            "сброс формул не восстанавливает потерянное HP."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.target = QComboBox()
        self.target.addItems(sorted(DEFAULT_FORMULAS))
        layout.addWidget(self.target)
        self.expression = QPlainTextEdit()
        self.expression.setMaximumHeight(140)
        layout.addWidget(self.expression)
        layout.addWidget(QLabel("Тестовые входы (JSON, стабильные ID):"))
        self.inputs = QPlainTextEdit('{"base_strength": 14, "dexterity_mod": 2}')
        self.inputs.setMaximumHeight(110)
        layout.addWidget(self.inputs)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status, 1)
        row = QHBoxLayout()
        self.test = QPushButton("Проверить пример")
        self.check = QPushButton("Предпросмотр проекта")
        self.apply = QPushButton("Применить")
        self.apply.setEnabled(False)
        self.reset = QPushButton("Стандартная")
        self.reset_all = QPushButton("Стандартный набор")
        self.reload = QPushButton("Загрузить сохранённые")
        for button in (self.test, self.check, self.apply, self.reset, self.reset_all, self.reload):
            row.addWidget(button)
        layout.addLayout(row)
        self.test.clicked.connect(self.test_example)
        self.check.clicked.connect(self.check_project)
        self.apply.clicked.connect(self.apply_project)
        self.reset.clicked.connect(self.reset_formula)
        self.reset_all.clicked.connect(self.reset_defaults)
        self.reload.clicked.connect(self.reload_saved)
        self.target.currentTextChanged.connect(self.load_formula)
        self.expression.textChanged.connect(self.capture)
        self.load_formula()
        service.core.replaced.connect(self.reject)

    def capture(self):
        if self._target is not None:
            source = self.expression.toPlainText()
            if source == DEFAULT_FORMULAS[self._target]:
                self.drafts.pop(self._target, None)
            else:
                self.drafts[self._target] = source
        self.preview = None
        self.apply.setEnabled(False)

    def load_formula(self, unused=None):
        self._target = None
        key = self.target.currentText()
        self.expression.setPlainText(self.drafts.get(key, DEFAULT_FORMULAS[key]))
        self._target = key

    def reset_formula(self):
        self.expression.setPlainText(DEFAULT_FORMULAS[self._target])

    def reset_defaults(self):
        self.drafts.clear()
        self.load_formula()
        self.capture()

    def reload_saved(self):
        self.rules_revision = self.service.rules.revision
        self.drafts = dict(self.service.rules.overrides)
        self.load_formula()
        self.capture()
        self.status.setText("Загружены сохранённые правила; локальный ввод отброшен.")

    def test_example(self):
        try:
            source = self.inputs.toPlainText()
            if len(source.encode("utf-8")) > 65536:
                raise ValueError("Пример слишком большой")
            inputs = json.loads(source)
            if not isinstance(inputs, dict) or len(inputs) > 256:
                raise ValueError("Нужен объект входных значений")
            if "hp_gains" in inputs and isinstance(inputs["hp_gains"], list):
                inputs["hp_gains"] = tuple(inputs["hp_gains"])
            expressions, order = compile_rules(tuple(sorted(self.drafts.items())))
            result = evaluate(expressions[self._target], inputs.get, FUNCTIONS)
            self.status.setText("Результат примера: " + str(result))
        except (ValueError, TypeError, RecursionError, CalculationError) as error:
            self.status.setText("Пример: " + str(error))

    def check_project(self):
        try:
            if self.generation != self.service.core.generation:
                raise ValueError("Проект изменился")
            self.preview = self.service.preview_rules(
                tuple(self.drafts.items()), expected_revision=self.rules_revision
            )
            self.apply.setEnabled(True)
            rows = self.preview[2]
            effects = self.service.preview_effects(self.preview)
            self.status.setText(
                f"Проверено карточек: {len(self.service.all())}. "
                f"Изменений расчётов: {len(effects)}.\n"
                + "\n".join(
                    f"{card} / {actor}: {key} "
                    f"{old.value if old.status == 'ok' else old.status} → "
                    f"{new.value if new.status == 'ok' else new.status}"
                    for card, actor, key, old, new in effects[:20]
                )
                + (f"\nЕщё изменений: {len(effects) - 20}" if len(effects) > 20 else "")
                + "\n"
                f"Ограничений текущего HP: {len(rows)}.\n"
                + "\n".join(f"{ref.actor_id[:8]}: {old} → {new}" for ref, old, new in rows[:30])
                + "\nНеизвестные/неподдержанные входы сохраняют явный статус."
            )
        except (ValueError, TypeError) as error:
            self.preview = None
            self.apply.setEnabled(False)
            self.status.setText(str(error))

    def apply_project(self):
        if self.preview is None:
            return
        try:
            self.service.apply_rules(self.preview)
            self.rules_revision = self.service.rules.revision
            self.preview = None
            self.apply.setEnabled(False)
            self.status.setText("Правила применены атомарно.")
        except ValueError as error:
            self.status.setText(str(error))
            self.preview = None
            self.apply.setEnabled(False)
