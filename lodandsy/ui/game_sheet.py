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
from lodandsy.ui.ability_block import AbilityBlock
from lodandsy.ui.card_fields import CardFieldsForm, field_text
from lodandsy.ui.character_header import CharacterHeader
from lodandsy.ui.conflict_bar import ConflictBar
from lodandsy.ui.game_labels import (
    error_text,
    field_label,
    field_surface,
    source_text,
    value_text,
)
from lodandsy.ui.icons import icon
from lodandsy.ui.semantic_edits import SemanticLineEdit


class GameSheet(QWidget):
    context_requested = Signal(object)
    edit_started = Signal(str)
    buffer_changed = Signal(str, str)
    commit_requested = Signal(str, str)
    cancel_requested = Signal(str)
    values_changed = Signal(object)
    inventory_requested = Signal()
    armor_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("gameSheet")
        self.setMinimumWidth(260)
        self.edit_active = lambda key: False
        self.actor_id = None
        self.card_type = None
        self.resource_inputs = {}
        self.header = CharacterHeader()
        self.forms = []
        self.tiles = {}
        self.results = {}
        self._columns = 0
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 12)
        outer.setSpacing(8)
        context_row = self.context_row = QGridLayout()
        self.context = QComboBox()
        self.context.setAccessibleName("Контекст игрового листа")
        self.context.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.context.setMinimumContentsLength(12)
        self.context.currentIndexChanged.connect(
            lambda i: self.context_requested.emit(self.context.itemData(i))
        )
        context_row.addWidget(self.context, 0, 0)
        self.base_button = QPushButton("К базе")
        self.base_button.clicked.connect(lambda: self.context_requested.emit(None))
        context_row.addWidget(self.base_button, 0, 1)
        self.inventory = QPushButton("Инвентарь участника")
        self.inventory.clicked.connect(self.inventory_requested)
        context_row.addWidget(self.inventory, 0, 2)
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
        if card_type != "object":
            self.flow.addWidget(self.header)
            for source, target in (
                (self.header.edit_started, self.edit_started),
                (self.header.buffer_changed, self.buffer_changed),
                (self.header.commit_requested, self.commit_requested),
                (self.header.cancel_requested, self.cancel_requested),
            ):
                source.connect(target)
            assigned.update(
                k for k in ("race", "class_or_role", "subclass", "level") if k in allowed
            )
        self.resource_settings = {}
        self.resource_inputs = {}
        self.metric_keys = []
        for key, title in (
            ("hp_max", "Хиты"),
            ("hp_temp", "Временные"),
            ("ac", "Класс Доспеха"),
            ("initiative", "Инициатива"),
            ("speed", "Скорость"),
            ("proficiency", "Мастерство"),
        ):
            if card_type == "object" and key in {"initiative", "proficiency"}:
                continue
            frame = QFrame()
            frame.setObjectName("resourceTile")
            frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(8, 6, 8, 6)
            layout.setSpacing(3)
            heading = QHBoxLayout()
            heading.addWidget(QLabel(title), 1)
            button = QToolButton()
            button.setIcon(icon("settings"))
            button.setFixedSize(24, 24)
            button.setObjectName("sheetResourceAction")
            button.setToolTip("Настройки: " + title)
            button.setAccessibleName("Настройки: " + title)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setObjectName("resourceValue")
            heading.addWidget(button)
            layout.addLayout(heading)
            values = QHBoxLayout()
            values.setContentsMargins(0, 0, 0, 0)
            font = QFont(self.font())
            font.setPointSize(17)
            font.setWeight(QFont.Weight.DemiBold)
            if key in {"hp_max", "hp_temp"}:
                state_key = "hp_current" if key == "hp_max" else "hp_temp"
                edit = SemanticLineEdit()
                edit.setMinimumWidth(0)
                edit.setMaximumWidth(68)
                edit.setFont(font)
                edit.setPlaceholderText("—")
                edit.setAccessibleName(field_label(state_key))
                edit.edit_started.connect(lambda k=state_key: self.edit_started.emit(k))
                edit.buffer_changed.connect(
                    lambda raw, k=state_key: self.buffer_changed.emit(k, raw)
                )
                edit.commit_requested.connect(
                    lambda raw, k=state_key: self.commit_requested.emit(k, raw)
                )
                edit.cancel_requested.connect(lambda k=state_key: self.cancel_requested.emit(k))
                values.addWidget(edit)
                self.resource_inputs[state_key] = edit
            label = QLabel("—")
            label.setFont(font)
            label.setMinimumWidth(0)
            if key != "hp_temp":
                values.addWidget(label)
                self.results[key] = label
            values.addStretch()
            layout.addLayout(values)
            if key == "hp_max":
                self.hp_progress = QProgressBar()
                self.hp_progress.setRange(0, 10000)
                self.hp_progress.setTextVisible(False)
                self.hp_progress.setMaximumHeight(4)
                layout.addWidget(self.hp_progress)
            if key in {"hp_max", "ac", "speed"}:
                body = QWidget()
                body.setVisible(False)
                details = QVBoxLayout(body)
                details.setContentsMargins(8, 4, 8, 4)
                mode = key + "_mode"
                base_keys = [k for k in (mode, key) if k in allowed]
                if key == "speed" and "speed_base" in allowed:
                    base_keys.append("speed_base")
                self.resource_base_forms.add(self._form(base_keys, details))
                assigned.update(base_keys)
                self._form((key + "_override",), details, scope="actor")
                self.resource_settings[key] = body
                button.clicked.connect(lambda checked=False, w=body: w.setVisible(w.isHidden()))
            else:
                button.hide()
            self.metric_keys.append(key)
            self.resource_frames.append(frame)
        self.flow.addLayout(self.resources)
        for key, body in self.resource_settings.items():
            if key != "ac":
                self.flow.addWidget(body)
            else:
                # The public AC action opens an addressed native dialog in the binding.
                body.setParent(self)
                body.hide()
                button = self.resource_frames[self.metric_keys.index("ac")].findChild(QToolButton)
                button.clicked.disconnect()
                button.clicked.connect(self.armor_requested)
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
                tile = AbilityBlock(key)
                tile.edit_started.connect(lambda k=key: self.edit_started.emit(k))
                tile.buffer_changed.connect(lambda raw, k=key: self.buffer_changed.emit(k, raw))
                tile.commit_requested.connect(lambda raw, k=key: self.commit_requested.emit(k, raw))
                tile.cancel_requested.connect(lambda k=key: self.cancel_requested.emit(k))
                tile.values_changed.connect(self.values_changed)
                self.tiles[key] = tile
            assigned.update(ABILITIES)
            assigned.update(a + "_save_proficient" for a in ABILITIES)
            assigned.update(s + "_proficiency" for s in SKILLS)
        self.flow.addWidget(self.ability_box)
        for group, title in (
            ("saves", "Спасброски"),
            ("skills", "Пассивное Восприятие"),
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
        result.update(self.header.controls)
        if self.actor_id:
            result.update(self.resource_inputs)
        result.update(
            {row.field: row.toggle for tile in self.tiles.values() for row in tile.rows.values()}
        )
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
        self.inventory.setVisible(True)
        self.inventory.setText("Инвентарь участника" if actor else "Базовый инвентарь")
        self.base_button.setVisible(actor is not None)
        self.header.set_values(card, actor, drafts, self.edit_active)
        for key, edit in self.resource_inputs.items():
            edit.setVisible(actor is not None)
            if actor:
                raw = drafts.get((actor.id, key), field_text(actor.value(key)))
                edit.set_value(raw, force=not self.edit_active(key))
                edit.setProperty("invalid", (actor.id, key) in drafts)
        for key, frame in zip(self.metric_keys, self.resource_frames):
            frame.setVisible(key != "hp_temp" or actor is not None)
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
        for tile in self.tiles.values():
            tile.render(card, actor, effective, drafts, self.edit_active)
        for key, label in self.results.items():
            value = effective.get(key)
            label.setText(
                value_text(
                    value,
                    sign=key in {*SKILLS, "initiative", "proficiency"} or key.endswith("_save"),
                )
            )
            automatic = effective.automatic.get(key)
            tooltip = source_text(value.source) + "\n" + error_text(value.diagnostic)
            if automatic:
                tooltip += "\nАвтоматически: " + value_text(automatic)
            label.setToolTip(tooltip)
        maximum = effective.get("hp_max")
        current = actor.value("hp_current") if actor else None
        if actor:
            self.results["hp_max"].setText(f"/ {value_text(maximum)}")
        else:
            self.results["hp_max"].setText(value_text(maximum))
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
                for key in ("passive_perception",)
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
        for widget in (self.context, self.base_button, self.inventory):
            self.context_row.removeWidget(widget)
        if width < 530:
            self.context_row.addWidget(self.context, 0, 0, 1, 2)
            self.context_row.addWidget(self.base_button, 1, 0)
            self.context_row.addWidget(
                self.inventory, 1, 1 if self.actor_id else 0, 1, 1 if self.actor_id else 2
            )
        else:
            self.context_row.addWidget(self.context, 0, 0)
            self.context_row.addWidget(self.base_button, 0, 1)
            self.context_row.addWidget(self.inventory, 0, 2)
        for column in range(3):
            self.context_row.setColumnStretch(column, int(column == 0))
        columns = 3 if width >= 810 else 2 if width >= 530 else 1
        if columns != self._columns:
            self._columns = columns
            for index, tile in enumerate(self.tiles.values()):
                self.ability_grid.addWidget(tile, index // columns, index % columns)
            for col in range(6):
                self.ability_grid.setColumnStretch(col, 1 if col < columns else 0)
        tile_height = max(
            (tile.minimumSizeHint().height() for tile in self.tiles.values()), default=0
        )
        for tile in self.tiles.values():
            tile.setFixedHeight(tile_height)
        self.header.reflow(width)
        resource_cols = 6 if width >= 810 else 3 if width >= 460 else 2
        visible = [
            (key, frame)
            for key, frame in zip(self.metric_keys, self.resource_frames)
            if key != "hp_temp" or self.actor_id is not None
        ]
        resource_cols = min(resource_cols, len(visible))
        for frame in self.resource_frames:
            self.resources.removeWidget(frame)
        metric_height = max(frame.minimumSizeHint().height() for _, frame in visible)
        for _, frame in visible:
            frame.setFixedHeight(metric_height)
        for index, (_, frame) in enumerate(visible):
            self.resources.addWidget(
                frame, index // resource_cols, index % resource_cols, Qt.AlignmentFlag.AlignTop
            )
        for col in range(6):
            self.resources.setColumnStretch(col, 1 if col < resource_cols else 0)
