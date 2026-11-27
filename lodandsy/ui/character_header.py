"""Editable native suggestions: text remains homebrew-friendly canonical text."""

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from lodandsy.domain.card_schema import permitted_fields
from lodandsy.ui.game_labels import field_label
from lodandsy.ui.icons import icon
from lodandsy.ui.semantic_edits import SemanticLineEdit

CLASSES = {
    "Варвар": ("Путь берсерка",),
    "Бард": ("Коллегия знаний",),
    "Жрец": ("Домен жизни",),
    "Друид": ("Круг земли",),
    "Воин": ("Чемпион",),
    "Монах": ("Путь открытой ладони",),
    "Паладин": ("Клятва преданности",),
    "Следопыт": ("Охотник",),
    "Плут": ("Вор",),
    "Чародей": ("Драконья кровь",),
    "Колдун": ("Исчадие",),
    "Волшебник": ("Школа воплощения",),
}
RACES = (
    "Человек",
    "Дварф",
    "Эльф",
    "Полурослик",
    "Драконорождённый",
    "Гном",
    "Полуэльф",
    "Полуорк",
    "Тифлинг",
)


class TextChoice(QComboBox):
    edit_started = Signal()
    buffer_changed = Signal(str)
    commit_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMinimumWidth(0)
        self.setMinimumContentsLength(6)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.input = SemanticLineEdit()
        self.input.setPlaceholderText("Не задано / свой вариант")
        self.setLineEdit(self.input)
        self.setProperty("sheetChoice", True)
        self.setCompleter(None)
        for source, target in (
            (self.input.edit_started, self.edit_started),
            (self.input.buffer_changed, self.buffer_changed),
            (self.input.commit_requested, self.commit_requested),
            (self.input.cancel_requested, self.cancel_requested),
        ):
            source.connect(target)
        self.activated.connect(lambda _: self.input.finish())
        self.options = ()
        self.inherited = False

    def showPopup(self):
        if not self.inherited:
            super().showPopup()

    def keyPressEvent(self, event):
        if self.inherited:
            event.ignore()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        if self.inherited:
            event.ignore()
        else:
            super().wheelEvent(event)

    def set_choices(self, choices):
        if tuple(choices) == self.options:
            return
        raw = self.input.text()
        blocker = QSignalBlocker(self)
        self.options = tuple(choices)
        self.clear()
        self.addItems(self.options)
        self.input.set_value(raw)
        del blocker

    def text(self):
        return self.input.text()

    def set_value(self, raw, *, force=False):
        self.input.set_value(raw, force=force)


class CharacterHeader(QWidget):
    edit_started = Signal(str)
    buffer_changed = Signal(str, str)
    commit_requested = Signal(str, str)
    cancel_requested = Signal(str)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(8)
        layout.addLayout(self.grid)
        self.controls, self.boxes = {}, []
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setObjectName("mutedCaption")
        layout.addWidget(self.warning)
        self.card_type = None

    def set_values(self, card, actor, drafts, active):
        keys = [
            key
            for key in ("race", "class_or_role", "subclass", "level")
            if key in permitted_fields(card.card_type)
        ]
        if list(self.controls) != keys:
            for key in keys:
                box = QWidget()
                layout = QHBoxLayout(box)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(3)
                control = SemanticLineEdit() if key == "level" else TextChoice()
                label = QLabel(field_label(key))
                label.setBuddy(control)
                glyph = QLabel()
                glyph.setPixmap(
                    icon(
                        {
                            "race": "race",
                            "class_or_role": "class",
                            "subclass": "subclass",
                            "level": "level",
                        }[key]
                    ).pixmap(16, 16)
                )
                layout.addWidget(glyph)
                layout.addWidget(label)
                layout.addWidget(control, 1)
                self.boxes.append(box)
                self.controls[key] = control
                control.setAccessibleName(field_label(key))
                control.setToolTip("Подсказки не выдают бонусы. Допустим собственный текст.")
                control.edit_started.connect(lambda k=key: self.edit_started.emit(k))
                control.buffer_changed.connect(lambda raw, k=key: self.buffer_changed.emit(k, raw))
                control.commit_requested.connect(
                    lambda raw, k=key: self.commit_requested.emit(k, raw)
                )
                control.cancel_requested.connect(lambda k=key: self.cancel_requested.emit(k))
        selected_class = card.value("class_or_role") if keys else None
        for key, control in self.controls.items():
            if isinstance(control, TextChoice):
                control.set_choices(
                    RACES
                    if key == "race"
                    else CLASSES
                    if key == "class_or_role"
                    else CLASSES.get(selected_class, ())
                )
            value = card.value(key)
            control.set_value(
                drafts.get((card.id, key), "" if value is None else str(value)),
                force=not active(key),
            )
            if isinstance(control, TextChoice):
                control.inherited = actor is not None
                control.input.setReadOnly(actor is not None)
            else:
                control.setReadOnly(actor is not None)
        subclass = card.value("subclass") if "subclass" in self.controls else None
        known = {name for values in CLASSES.values() for name in values}
        mismatch = subclass in known and subclass not in CLASSES.get(selected_class, ())
        self.warning.setText(
            "Архетип сохранён от другого класса. Выберите подходящий или свой вариант."
            if mismatch
            else ""
        )
        self.warning.setVisible(mismatch)

    def reflow(self, width):
        columns = 4 if width >= 1100 else 2 if width >= 620 else 1
        for i, box in enumerate(self.boxes):
            self.grid.addWidget(box, i // columns, i % columns)
        for i in range(4):
            self.grid.setColumnStretch(i, 1 if i < columns else 0)
