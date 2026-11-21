"""Compact native game sheet. Owns presentation only, never canonical values."""

from PySide6.QtCore import QEvent, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.domain.card_schema import ABILITIES, SKILLS, field_definition, permitted_fields
from lodandsy.ui.card_fields import CardFieldsForm, field_text
from lodandsy.ui.conflict_bar import ConflictBar
from lodandsy.ui.game_labels import (
    ABILITY_NAMES,
    ABILITY_SHORT,
    error_text,
    field_label,
    field_surface,
    source_text,
    value_text,
)
from lodandsy.ui.semantic_edits import SemanticLineEdit


class AbilityTile(QFrame):
    edit_started = Signal()
    buffer_changed = Signal(str)
    commit_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self, key):
        super().__init__()
        self.key = key
        self.setObjectName("abilityTile")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)
        self.result = QLabel("—")
        font = QFont(self.font())
        font.setPointSize(18)
        font.setWeight(QFont.Weight.DemiBold)
        self.result.setFont(font)
        self.result.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.result)
        self.caption = QLabel(ABILITY_SHORT[key])
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setToolTip(ABILITY_NAMES[key])
        layout.addWidget(self.caption)
        self.base = QLabel()
        self.base.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.base)
        self.edit_button = QToolButton()
        self.edit_button.setText("Изменить базу")
        self.edit_button.setAccessibleName("Изменить · " + ABILITY_NAMES[key])
        self.edit = SemanticLineEdit()
        self.edit.setAccessibleName("Базовое значение · " + ABILITY_NAMES[key])
        self.edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit.hide()
        self.edit_button.clicked.connect(self.begin_edit)
        self.edit.edit_started.connect(self.edit_started)
        self.edit.buffer_changed.connect(self.buffer_changed)
        self.edit.commit_requested.connect(self._commit)
        self.edit.cancel_requested.connect(self._cancel)
        layout.addWidget(self.edit_button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.edit)

    def begin_edit(self):
        self.edit.show()
        self.edit_button.hide()
        self.edit.setFocus()
        self.edit.selectAll()

    def _commit(self, raw):
        self.commit_requested.emit(raw)
        if not self.edit.property("invalid"):
            self.edit.hide()
            self.edit_button.show()

    def _cancel(self):
        self.cancel_requested.emit()
        self.edit.hide()
        self.edit_button.show()


class GameSheet(QWidget):
    context_requested = Signal(object)
    edit_started = Signal(str)
    buffer_changed = Signal(str, str)
    commit_requested = Signal(str, str)
    cancel_requested = Signal(str)
    values_changed = Signal(object)
    inventory_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("gameSheet")
        self.setMinimumWidth(260)
        self.edit_active = lambda key: False
        self.actor_id = None
        self.card_type = None
        self.forms = []
        self.tiles = {}
        self.results = {}
        self._columns = 0
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 12)
        outer.setSpacing(8)
        context_row = QHBoxLayout()
        self.context = QComboBox()
        self.context.setAccessibleName("Контекст игрового листа")
        self.context.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.context.setMinimumContentsLength(12)
        self.context.currentIndexChanged.connect(
            lambda i: self.context_requested.emit(self.context.itemData(i))
        )
        context_row.addWidget(self.context, 1)
        self.inventory = QPushButton("Инвентарь участника")
        self.inventory.clicked.connect(self.inventory_requested)
        context_row.addWidget(self.inventory)
        outer.addLayout(context_row)
        self.context_note = QLabel()
        self.context_note.setWordWrap(True)
        outer.addWidget(self.context_note)
        self.notice = QLabel()
        self.notice.setObjectName("errorNotice")
        self.notice.setWordWrap(True)
        self.notice.hide()
        outer.addWidget(self.notice)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.flow = QVBoxLayout(self.content)
        self.flow.setContentsMargins(0, 0, 0, 0)
        self.flow.setSpacing(12)
        self.flow.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.content)
        self.scroll.viewport().installEventFilter(self)
        outer.addWidget(self.scroll, 1)
        self.conflicts = ConflictBar()
        outer.addWidget(self.conflicts)
        self.setStyleSheet("""
            QFrame#abilityTile, QFrame#resourceTile {
                border:1px solid rgba(128,128,128,72); border-radius:6px;
                background:palette(base);
            }
            QFrame#abilityTile QLineEdit { padding:4px; }
            QToolButton#sheetDisclosure { border:0; padding:6px 0; font-weight:600; }
        """)

    def _form(self, keys, parent_layout, *, scope="card"):
        form = CardFieldsForm(groups=False)
        form.edit_active = self.edit_active
        form.edit_started.connect(self.edit_started)
        form.buffer_changed.connect(self.buffer_changed)
        form.commit_requested.connect(self.commit_requested)
        form.cancel_requested.connect(self.cancel_requested)
        form.edited.connect(self.values_changed)
        parent_layout.addWidget(form)
        self.forms.append((form, tuple(keys), scope))
        return form

    def _section(self, title, *, opened=False):
        button = QToolButton()
        button.setObjectName("sheetDisclosure")
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setText(title)
        button.setCheckable(True)
        button.setChecked(opened)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        button.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow)
        button.toggled.connect(body.setVisible)
        button.toggled.connect(
            lambda checked: button.setArrowType(
                Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
            )
        )
        body.setVisible(opened)
        self.flow.addWidget(button)
        self.flow.addWidget(body)
        return layout

    def _build(self, card_type):
        while self.flow.count():
            item = self.flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.forms, self.tiles, self.results = [], {}, {}
        self.card_type = card_type
        allowed = permitted_fields(card_type)
        self.resources = QGridLayout()
        self.resources.setSpacing(8)
        self.resource_frames = []
        self.resource_base_forms = set()
        self.override_forms = {}
        assigned = set()
        for key, title in (("hp_max", "Хиты"), ("ac", "Класс Доспеха"), ("speed", "Скорость")):
            frame = QFrame()
            frame.setObjectName("resourceTile")
            frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(10, 8, 10, 8)
            layout.setSpacing(5)
            layout.addWidget(QLabel(title))
            label = QLabel("—")
            font = QFont(self.font())
            font.setPointSize(17)
            font.setWeight(QFont.Weight.DemiBold)
            label.setFont(font)
            layout.addWidget(label)
            self.results[key] = label
            mode = key + "_mode"
            base_keys = [k for k in (mode, key) if k in allowed]
            if key == "speed" and "speed_base" in allowed:
                base_keys.append("speed_base")
            self.resource_base_forms.add(self._form(base_keys, layout))
            assigned.update(base_keys)
            if key == "hp_max":
                self.hp_progress = QProgressBar()
                self.hp_progress.setRange(0, 10000)
                self.hp_progress.setTextVisible(False)
                self.hp_progress.setMaximumHeight(7)
                layout.addWidget(self.hp_progress)
                self._form(("hp_current", "hp_temp"), layout, scope="actor")
            toggle = QToolButton()
            toggle.setText("Личный итог…")
            toggle.setToolTip("Пустое значение наследует карточку; личное итоговое имеет приоритет")
            toggle.setCheckable(True)
            layout.addWidget(toggle)
            override_form = self._form((key + "_override",), layout, scope="actor")
            toggle.toggled.connect(override_form.setVisible)
            self.override_forms[override_form] = toggle
            self.resource_frames.append(frame)
        self.flow.addLayout(self.resources)
        self.quick = QLabel()
        self.quick.setWordWrap(True)
        self.quick.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.flow.addWidget(self.quick)
        self.ability_grid = QGridLayout()
        self.ability_grid.setSpacing(8)
        self.ability_grid.setContentsMargins(0, 0, 0, 0)
        self.ability_box = QWidget()
        self.ability_box.setLayout(self.ability_grid)
        if card_type != "object":
            for key in ABILITIES:
                tile = AbilityTile(key)
                tile.edit_started.connect(lambda k=key: self.edit_started.emit(k))
                tile.buffer_changed.connect(lambda raw, k=key: self.buffer_changed.emit(k, raw))
                tile.commit_requested.connect(lambda raw, k=key: self.commit_requested.emit(k, raw))
                tile.cancel_requested.connect(lambda k=key: self.cancel_requested.emit(k))
                self.tiles[key] = tile
            assigned.update(ABILITIES)
        self.flow.addWidget(self.ability_box)
        for group, title in (
            ("saves", "Спасброски"),
            ("skills", "Навыки"),
            ("defence", "Броня и защита"),
            ("hp_inputs", "Прогрессия хитов по уровням"),
            ("character", "Персонаж: уровень, опыт и происхождение"),
            ("attack", "Атаки"),
            ("spell", "Заклинания"),
            ("identity", "Игрок и постоянный участник"),
            ("abilities", "Дополнительные характеристики объекта"),
        ):
            keys = [
                key
                for key in allowed - assigned
                if field_definition(key).group == group and field_surface(key) == "attributes"
            ]
            if card_type == "object":
                keys = [key for key in keys if key != "player"]
            if not keys:
                continue
            keys.sort(key=lambda key: (key != "level", key != "hp_gains", field_label(key)))
            layout = self._section(title)
            self._form(keys, layout)
            assigned.update(keys)
            for field in keys:
                target = field.removesuffix("_proficiency").removesuffix("_proficient")
                if target in {*SKILLS, *(a + "_save" for a in ABILITIES)}:
                    result = QLabel()
                    self.results[target] = result
                    result_row = QHBoxLayout()
                    result_row.addWidget(QLabel("Итог · " + field_label(target)), 1)
                    result_row.addWidget(result)
                    layout.addLayout(result_row)
        layout = self._section("Нагрузка и источники")
        self.sources = QLabel()
        self.sources.setWordWrap(True)
        self.sources.setTextFormat(Qt.TextFormat.PlainText)
        self.sources.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.sources)
        self._columns = 0
        self._reflow()

    @property
    def controls(self):
        result = {key: widget for form, _, _ in self.forms for key, widget in form.controls.items()}
        result.update({key: tile.edit for key, tile in self.tiles.items()})
        return result

    def set_values(self, card, actor, effective, drafts):
        if self.card_type != card.card_type:
            self._build(card.card_type)
        self.actor_id = actor.id if actor else None
        blocker = QSignalBlocker(self.context)
        options = [
            ("Базовая карточка", None),
            *(("Участник: " + a.name, a.id) for a in card.actors),
        ]
        if [
            (self.context.itemText(i), self.context.itemData(i))
            for i in range(self.context.count())
        ] != options:
            self.context.clear()
            for label, key in options:
                self.context.addItem(label, key)
        self.context.setCurrentIndex(self.context.findData(self.actor_id))
        self.context.setToolTip(self.context.currentText())
        del blocker
        self.context_note.setText(
            "Общие значения всех участников. Текущие и временные хиты — после выбора участника."
            if actor is None
            else "База наследуется от карточки. Для её изменения выберите «Базовая карточка»."
        )
        self.inventory.setVisible(actor is not None and actor.inventory_id is not None)
        for form, keys, scope in self.forms:
            if scope == "actor":
                form.setVisible(actor is not None)
                if form in self.override_forms:
                    self.override_forms[form].setVisible(actor is not None)
                if actor is None:
                    continue
                read, owner = actor.value, actor.id
            else:
                read, owner = card.value, card.id
            form.set_values(owner, read, keys, drafts)
            form.setEnabled(scope == "actor" or actor is None)
            if form in self.resource_base_forms:
                form.setVisible(actor is None)
            if form in self.override_forms:
                toggle = self.override_forms[form]
                toggle.setVisible(actor is not None)
                form.setVisible(actor is not None and toggle.isChecked())
            for key in ("hp_max", "ac", "speed"):
                if key in keys and key + "_mode" in keys:
                    form.set_field_visible(key, card.value(key + "_mode") == "manual")
            if "speed_base" in keys:
                form.set_field_visible("speed_base", card.value("speed_mode") == "auto")
        for key, tile in self.tiles.items():
            score, modifier = effective.get(key), effective.get(key + "_mod")
            tile.result.setText(f"{value_text(modifier, sign=True)} ({value_text(score)})")
            tile.base.setText("База " + str(card.value(key)))
            tile.setToolTip(
                ABILITY_NAMES[key]
                + "\n"
                + source_text(score.source)
                + "\n"
                + error_text(score.diagnostic)
            )
            raw = drafts.get((card.id, key), field_text(card.value(key)))
            tile.edit.set_value(raw, force=not self.edit_active(key))
            tile.edit.setProperty("invalid", (card.id, key) in drafts)
            tile.edit_button.setVisible(actor is None and not tile.edit.isVisible())
            if actor is not None:
                tile.edit.hide()
        for key, label in self.results.items():
            value = effective.get(key)
            label.setText(value_text(value, sign=key in SKILLS or key.endswith("_save")))
            automatic = effective.automatic.get(key)
            tooltip = source_text(value.source) + "\n" + error_text(value.diagnostic)
            if automatic:
                tooltip += "\nАвтоматически: " + value_text(automatic)
            label.setToolTip(tooltip)
        maximum = effective.get("hp_max")
        current = actor.value("hp_current") if actor else None
        if actor:
            self.results["hp_max"].setText(
                f"{current if current is not None else '—'} / {value_text(maximum)}"
            )
        else:
            self.results["hp_max"].setText("Максимум " + value_text(maximum))
        ratio = (
            int(10000 * current / maximum.value)
            if current is not None and maximum.status == "ok" and maximum.value > 0
            else 0
        )
        self.hp_progress.setValue(max(0, min(10000, ratio)))
        self.hp_progress.setVisible(actor is not None)
        speed = effective.get("speed")
        if speed.status == "ok":
            self.results["speed"].setText(f"{speed.value} фт.")
            self.results["speed"].setToolTip(
                self.results["speed"].toolTip()
                + f"\n{speed.value} фт. = {speed.value * 0.3048:g} м"
            )
        self.quick.setText(
            " · ".join(
                field_label(key)
                + " "
                + value_text(effective.get(key), sign=key in {"initiative", "proficiency"})
                for key in ("initiative", "level", "proficiency", "passive_perception")
                if card.card_type != "object"
            )
        )
        self.quick.setVisible(card.card_type != "object")
        self.ability_box.setVisible(card.card_type != "object")
        self.sources.setText(
            "\n".join(
                f"{field_label(key)}: {value_text(value)} · {source_text(value.source)}"
                + (" · " + error_text(value.diagnostic) if value.diagnostic else "")
                for key, value in effective.values.items()
                if key in effective.automatic
                and (
                    card.card_type != "object" or key in {"hp_max", "ac", "speed", "carried_weight"}
                )
            )
        )
        self._reflow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.card_type:
            self._reflow()

    def eventFilter(self, watched, event):
        if (
            watched is self.scroll.viewport()
            and event.type() == QEvent.Type.Resize
            and self.card_type
        ):
            self._reflow()
        return super().eventFilter(watched, event)

    def _reflow(self):
        width = self.scroll.viewport().width()
        columns = 6 if width >= 810 else 3 if width >= 430 else 2
        if columns != self._columns:
            self._columns = columns
            for index, tile in enumerate(self.tiles.values()):
                self.ability_grid.addWidget(tile, index // columns, index % columns)
            for col in range(6):
                self.ability_grid.setColumnStretch(col, 1 if col < columns else 0)
        resource_cols = 3 if width >= 690 else 2 if width >= 430 else 1
        for index, frame in enumerate(self.resource_frames):
            self.resources.addWidget(
                frame, index // resource_cols, index % resource_cols, Qt.AlignmentFlag.AlignTop
            )
        for col in range(3):
            self.resources.setColumnStretch(col, 1 if col < resource_cols else 0)
