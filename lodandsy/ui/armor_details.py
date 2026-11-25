"""Read-only AC provenance with addressed manual controls supplied by the sheet."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from lodandsy.domain.formula import CalculationError
from lodandsy.domain.rules_5e14 import armor_dexterity
from lodandsy.ui.game_labels import CHOICES, error_text, signed, source_text, value_text


class ArmorDetails(QDialog):
    inventory_requested = Signal()

    def __init__(self, controls, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Класс Доспеха · расчёт и ручной итог")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)
        self.context = QLabel()
        self.context.setTextFormat(Qt.TextFormat.PlainText)
        self.context.setWordWrap(True)
        layout.addWidget(self.context)
        self.result = QLabel()
        self.result.setObjectName("pageHeading")
        layout.addWidget(self.result)
        self.details = QLabel()
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        layout.addWidget(controls)
        controls.show()
        self.note = QLabel(
            "Ручной КД — окончательный итог, включая все бонусы. "
            "Пустой личный итог наследует режим карточки. Доспех и щит меняются в инвентаре."
        )
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        actions = QHBoxLayout()
        inventory = QPushButton("Открыть инвентарь")
        inventory.clicked.connect(self.inventory_requested)
        actions.addWidget(inventory)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.close)
        actions.addWidget(close)
        layout.addLayout(actions)

    def render(self, card, actor, effective, inputs):
        self.context.setText("Участник: " + actor.name if actor else "Базовая карточка")
        value, automatic = effective.get("ac"), effective.automatic.get("ac")
        self.result.setText("КД " + value_text(value))
        facts = inputs.get("equipment")
        lines = []
        if facts:
            lines.append("Доспех: " + (facts.armor.label if facts.armor else "не надет"))
            lines.append("Категория: " + CHOICES.get(facts.armor_type, facts.armor_type))
            lines.append(
                "Основа: "
                + (str(facts.armor_base) if facts.armor_base is not None else "Не задано")
            )
            lines.append("Щит: " + (facts.shield_item.label if facts.shield_item else "не надет"))
            if facts.shield:
                lines.append("Вклад щита: " + signed(facts.shield_bonus))
            if facts.diagnostic:
                lines.append(error_text(facts.diagnostic))
        dexterity = effective.get("dexterity_mod")
        lines.append("Модификатор Ловкости: " + value_text(dexterity, sign=True))
        if facts and dexterity.status == "ok" and not facts.diagnostic:
            try:
                contribution = armor_dexterity(facts.armor_type, dexterity.value)
                lines.append("Учтено Ловкости: " + signed(contribution))
            except CalculationError as error:
                lines.append(error_text(error))
        for source in inputs.get("sources", ()):
            modifier = source.modifier
            if modifier.target == "ac":
                lines.append(
                    f"{source.label}: {CHOICES.get(modifier.operation, modifier.operation)} "
                    f"{modifier.operand:g}"
                )
        if automatic:
            lines.append("Автоматический КД: " + value_text(automatic))
            if automatic.diagnostic:
                lines.append(error_text(automatic.diagnostic))
        lines.append("Источник итога: " + source_text(value.source))
        self.details.setText("\n".join(lines))
