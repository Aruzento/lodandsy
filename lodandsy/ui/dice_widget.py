from PySide6.QtCore import QSignalBlocker, QSize, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.application.clipboard import copy_text
from lodandsy.domain.dice import FACES, DiceConfig, roll_dice
from lodandsy.ui.icons import icon


class DiceWidget(QWidget):
    def __init__(self, runtime=None):
        super().__init__()
        self.setObjectName("diceTool")
        self.runtime = runtime if runtime is not None else {}
        self.runtime.setdefault("config", DiceConfig())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        self.content = QWidget()
        self.content.setMaximumWidth(760)
        outer = QHBoxLayout(page)
        outer.setContentsMargins(24, 36, 24, 24)
        outer.addStretch(1)
        outer.addWidget(self.content, 20)
        outer.addStretch(1)
        scroll.setWidget(page)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        crumb = QHBoxLayout()
        caption = QLabel("Инструменты / Кубики")
        caption.setObjectName("mutedCaption")
        crumb.addWidget(caption, 1)
        clear = QToolButton()
        clear.setText("Очистить")
        clear.clicked.connect(self.clear_counts)
        crumb.addWidget(clear)
        layout.addLayout(crumb)
        heading = QLabel("Бросок кубиков")
        heading.setObjectName("pageHeading")
        layout.addWidget(heading)
        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        self.tiles, self.counts = [], {}
        for faces in FACES:
            tile = QWidget()
            tile.setObjectName("diceFace")
            column = QVBoxLayout(tile)
            column.setContentsMargins(10, 10, 10, 10)
            button = QToolButton()
            button.setIcon(icon(f"d{faces}", 24))
            button.setIconSize(QSize(24, 24))
            button.setText(f"d{faces}")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setStyleSheet("font-size:22px;font-weight:600")
            button.setAccessibleName(f"Добавить d{faces}")
            button.setToolTip(button.accessibleName())
            box = QSpinBox()
            box.setRange(0, 1000)
            box.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            box.setAccessibleName(f"Количество d{faces}")
            self.counts[faces] = box
            button.clicked.connect(lambda checked=False, f=faces: self.counts[f].stepUp())
            box.valueChanged.connect(self._edited)
            column.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            count_row = QHBoxLayout()
            minus, plus = QToolButton(), QToolButton()
            minus.setText("−")
            plus.setText("+")
            minus.setAccessibleName(f"Уменьшить количество d{faces}")
            plus.setAccessibleName(f"Увеличить количество d{faces}")
            minus.clicked.connect(box.stepDown)
            plus.clicked.connect(box.stepUp)
            count_row.addWidget(minus)
            count_row.addWidget(box, 1)
            count_row.addWidget(plus)
            column.addLayout(count_row)
            self.tiles.append(tile)
        modifier_tile = QWidget()
        modifier_tile.setObjectName("diceFace")
        modifier_layout = QVBoxLayout(modifier_tile)
        label = QLabel("Модификатор")
        label.setObjectName("mutedCaption")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        modifier_layout.addWidget(label)
        self.modifier = QSpinBox()
        self.modifier.setRange(-1000000000, 1000000000)
        self.modifier.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.modifier.setAccessibleName("Модификатор броска")
        self.modifier.valueChanged.connect(self._edited)
        modifier_layout.addWidget(self.modifier)
        self.tiles.append(modifier_tile)
        layout.addLayout(self.grid)
        buttons = QHBoxLayout()
        self.formula = QLabel()
        self.formula.setWordWrap(True)
        self.formula.setTextFormat(Qt.TextFormat.PlainText)
        buttons.addWidget(self.formula, 1)
        self.roll = QPushButton("Бросить кубики")
        self.roll.setObjectName("primaryAction")
        self.roll.clicked.connect(self.throw)
        buttons.addWidget(self.roll)
        layout.addLayout(buttons)
        result_panel = QWidget()
        result_panel.setObjectName("diceResult")
        result_row = QHBoxLayout(result_panel)
        result_row.setContentsMargins(16, 12, 16, 12)
        self.total = QLabel(str(self.runtime.get("total", "—")))
        self.total.setObjectName("diceTotal")
        result_row.addWidget(self.total)
        self.details = QLabel(self.runtime.get("last", "Результат броска появится здесь"))
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        self.details.setWordWrap(True)
        result_row.addWidget(self.details, 1)
        self.repeat = QToolButton()
        self.repeat.setIcon(icon("redo"))
        self.repeat.setToolTip("Повторить бросок")
        self.repeat.setAccessibleName(self.repeat.toolTip())
        self.repeat.clicked.connect(self.throw)
        self.copy = QToolButton()
        self.copy.setIcon(icon("link"))
        self.copy.setToolTip("Копировать результат")
        self.copy.setAccessibleName(self.copy.toolTip())
        self.copy.clicked.connect(lambda: copy_text(self.runtime.get("last", "")))
        result_row.addWidget(self.repeat)
        result_row.addWidget(self.copy)
        layout.addWidget(result_panel)
        history_label = QLabel("ИСТОРИЯ БРОСКОВ")
        history_label.setObjectName("mutedCaption")
        layout.addWidget(history_label)
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        self.result.setMaximumHeight(150)
        self.result.setAccessibleName("Отдельные результаты и история текущей сессии")
        self.result.setPlainText("\n\n".join(reversed(self.runtime.get("history", []))))
        layout.addWidget(self.result)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setObjectName("errorNotice")
        layout.addWidget(self.error)
        layout.addStretch(1)
        self._columns = 0
        self._layout_faces(4)
        self._restore_config()
        self.copy.setEnabled(bool(self.runtime.get("last")))

    def _layout_faces(self, columns):
        if columns == self._columns:
            return
        self._columns = columns
        for tile in self.tiles:
            self.grid.removeWidget(tile)
        for i, tile in enumerate(self.tiles):
            self.grid.addWidget(tile, i // columns, i % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_faces(max(2, min(4, self.width() // 120)))

    def _restore_config(self):
        config = self.runtime["config"]
        for faces, value in zip(FACES, config.counts):
            blocker = QSignalBlocker(self.counts[faces])
            self.counts[faces].setValue(value)
            del blocker
        blocker = QSignalBlocker(self.modifier)
        self.modifier.setValue(config.modifier)
        del blocker
        self.formula.setText(config.expression())

    def _edited(self):
        if not hasattr(self, "modifier"):
            return
        try:
            config = DiceConfig(tuple(self.counts[f].value() for f in FACES), self.modifier.value())
            self.runtime["config"] = config
            self.formula.setText(config.expression())
            self.error.clear()
        except ValueError as error:
            self._restore_config()
            self.error.setText(str(error))

    def clear_counts(self):
        self.runtime["config"] = DiceConfig((0,) * 7, 0)
        self._restore_config()

    def throw(self):
        try:
            result = roll_dice(self.runtime["config"])
            text = result.text()
            self.runtime["last"] = text
            self.runtime["total"] = result.total
            history = self.runtime.setdefault("history", [])
            history.append(text)
            del history[:-50]
            self.total.setText(str(result.total))
            self.details.setText(text)
            self.result.setPlainText("\n\n".join(reversed(history)))
            self.copy.setEnabled(True)
            self.error.clear()
        except ValueError as error:
            self.error.setText(str(error))
