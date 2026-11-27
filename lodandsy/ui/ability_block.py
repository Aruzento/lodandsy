"""Native ability block: one input and addressed proficiency/result rows."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.domain.card_schema import SKILLS
from lodandsy.ui.game_labels import ABILITY_NAMES, SKILL_NAMES, source_text, value_text
from lodandsy.ui.semantic_edits import SemanticLineEdit


class SheetDisclosure(QToolButton):
    def __init__(self, title, body, *, opened=False):
        super().__init__()
        self.body = body
        self.setObjectName("sheetDisclosure")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setText(title)
        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setChecked(opened)
        self.toggled.connect(self._display)
        self._display(opened)

    def _display(self, opened):
        self.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow)
        self.body.setVisible(opened)


class ProficiencyRow(QFrame):
    changed = Signal(object)

    def __init__(self, field, title, *, saving=False):
        super().__init__()
        self.field, self.saving, self.state = field, saving, 0
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        self.toggle = QToolButton()
        self.toggle.setFixedSize(26, 24)
        self.toggle.setObjectName("proficiencyToggle")
        self.toggle.clicked.connect(self.cycle)
        row.addWidget(self.toggle)
        self.caption = QLabel(title)
        self.caption.setMinimumWidth(0)
        self.caption.setWordWrap(True)
        row.addWidget(self.caption, 1)
        self.result = QLabel("—")
        self.result.setMinimumWidth(30)
        self.result.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.result.setObjectName("proficiencyResult")
        row.addWidget(self.result)
        self.title = title

    def cycle(self):
        value = not self.state if self.saving else (self.state + 1) % 3
        self.changed.emit({self.field: value})

    def render(self, value, result, *, inherited=False):
        self.state = int(value)
        self.toggle.setText(("○", "●", "◆")[self.state])
        state = ("Нет владения", "Владение", "Компетентность")[self.state]
        action = "Наследуется от базовой карточки" if inherited else "Нажмите для переключения"
        self.toggle.setAccessibleName(f"{self.title}: {state}")
        self.toggle.setToolTip(f"{self.title} · {state}\n{action}")
        self.toggle.setEnabled(not inherited)
        self.result.setText(value_text(result, sign=True))
        self.result.setToolTip(result.diagnostic or "Вычисленный итог")


class AbilityBlock(QFrame):
    edit_started = Signal()
    buffer_changed = Signal(str)
    commit_requested = Signal(str)
    cancel_requested = Signal()
    values_changed = Signal(object)

    def __init__(self, key):
        super().__init__()
        self.key = key
        self.setObjectName("abilityTile")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        heading = QHBoxLayout()
        details = QWidget()
        detail_layout = QVBoxLayout(details)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(2)
        self.disclosure = SheetDisclosure(ABILITY_NAMES[key], details)
        heading.addWidget(self.disclosure, 1)
        self.result = QLabel("—")
        font = QFont(self.font())
        font.setPointSize(19)
        font.setWeight(QFont.Weight.DemiBold)
        self.result.setFont(font)
        self.result.setMinimumWidth(43)
        heading.addWidget(self.result)
        self.edit = SemanticLineEdit()
        self.edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit.setFixedWidth(48)
        self.edit.setAccessibleName("Базовое значение · " + ABILITY_NAMES[key])
        self.edit.setToolTip("Общее базовое значение. Enter/Tab — сохранить, Escape — отменить")
        self.edit.edit_started.connect(self.edit_started)
        self.edit.buffer_changed.connect(self.buffer_changed)
        self.edit.commit_requested.connect(self.commit_requested)
        self.edit.cancel_requested.connect(self.cancel_requested)
        heading.addWidget(self.edit)
        layout.addLayout(heading)
        self.base = QLabel()
        self.base.setObjectName("mutedCaption")
        self.base.setWordWrap(True)
        detail_layout.addWidget(self.base)
        self.rows = {}
        for target, field, title, saving in (
            (key + "_save", key + "_save_proficient", "Спасбросок", True),
            *(
                (skill, skill + "_proficiency", SKILL_NAMES[skill], False)
                for skill, ability in sorted(SKILLS.items(), key=lambda pair: SKILL_NAMES[pair[0]])
                if ability == key
            ),
        ):
            row = ProficiencyRow(field, title, saving=saving)
            row.changed.connect(self.values_changed)
            self.rows[target] = row
            detail_layout.addWidget(row)
        layout.addWidget(details)

    def render(self, card, actor, effective, drafts, active):
        score, modifier = effective.get(self.key), effective.get(self.key + "_mod")
        self.result.setText(value_text(modifier, sign=True))
        self.result.setToolTip(modifier.diagnostic or "Вычисленный модификатор")
        base = card.value(self.key)
        self.edit.setReadOnly(actor is not None)
        self.edit.setAccessibleName(
            ("Итоговое значение · " if actor else "Базовое значение · ") + ABILITY_NAMES[self.key]
        )
        raw = (
            (str(score.value) if score.status == "ok" else "—")
            if actor
            else drafts.get((card.id, self.key), str(base))
        )
        self.edit.set_value(raw, force=not active(self.key))
        self.edit.setToolTip(
            f"База {base} из карточки. {source_text(score.source)}. Для общей правки — «К базе»."
            if actor
            else "Общее базовое значение. Enter/Tab — сохранить, Escape — отменить"
        )
        self.edit.setProperty("invalid", (card.id, self.key) in drafts)
        if actor:
            self.base.setText(
                f"База {base} → итог {score.value}"
                if score.status == "ok" and score.value != base
                else ""
            )
        elif score.status == "ok" and score.value != base:
            self.base.setText(f"Итог с источниками: {score.value}")
        else:
            self.base.clear()
        self.base.setVisible(bool(self.base.text()))
        for key, row in self.rows.items():
            row.render(card.value(row.field), effective.get(key), inherited=actor is not None)
