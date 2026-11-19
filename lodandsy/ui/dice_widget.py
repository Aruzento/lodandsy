from PySide6.QtCore import QSignalBlocker, QSize, Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        heading = QLabel("Кубики")
        heading.setStyleSheet("font-size:22px;font-weight:600")
        layout.addWidget(heading)
        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        self.tiles = []
        self.counts = {}
        for faces in FACES:
            tile = QWidget()
            tile.setObjectName("diceFace")
            column = QVBoxLayout(tile)
            column.setContentsMargins(8, 8, 8, 8)
            button = QToolButton()
            button.setIcon(icon(f"d{faces}", 36))
            button.setIconSize(QSize(36, 36))
            button.setText(f"d{faces}")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setAccessibleName(f"Добавить d{faces}")
            button.setToolTip(button.accessibleName())
            box = QSpinBox()
            box.setRange(0, 1000)
            box.setAccessibleName(f"Количество d{faces}")
            self.counts[faces] = box
            button.clicked.connect(
                lambda checked=False, f=faces: self.counts[f].setValue(self.counts[f].value() + 1)
            )
            box.valueChanged.connect(self._edited)
            column.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            column.addWidget(box)
            self.tiles.append(tile)
        layout.addLayout(self.grid)
        row = QHBoxLayout()
        row.addWidget(QLabel("Модификатор"))
        self.modifier = QSpinBox()
        self.modifier.setRange(-1000000000, 1000000000)
        self.modifier.setAccessibleName("Модификатор броска")
        self.modifier.valueChanged.connect(self._edited)
        row.addWidget(self.modifier)
        row.addStretch()
        layout.addLayout(row)
        result_row = QHBoxLayout()
        self.formula = QLabel()
        self.formula.setWordWrap(True)
        self.formula.setTextFormat(Qt.TextFormat.PlainText)
        self.total = QLabel(str(self.runtime.get("total", "—")))
        self.total.setStyleSheet("font-size:36px;font-weight:600;color:#ceb075")
        result_row.addWidget(self.formula, 1)
        result_row.addWidget(self.total)
        layout.addLayout(result_row)
        buttons = QHBoxLayout()
        self.roll = QPushButton("Бросить")
        self.roll.setObjectName("primaryAction")
        self.roll.clicked.connect(self.throw)
        self.repeat = QPushButton("Повторить")
        self.repeat.clicked.connect(self.throw)
        clear = QToolButton()
        clear.setText("Очистить")
        clear.clicked.connect(self.clear_counts)
        self.copy = QToolButton()
        self.copy.setIcon(icon("link"))
        self.copy.setToolTip("Копировать результат")
        self.copy.setAccessibleName(self.copy.toolTip())
        self.copy.clicked.connect(lambda: copy_text(self.runtime.get("last", "")))
        for button in (self.roll, self.repeat, clear, self.copy):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        self.result.setAccessibleName("Отдельные результаты и история текущей сессии")
        self.result.setPlainText("\n\n".join(reversed(self.runtime.get("history", []))))
        layout.addWidget(self.result, 1)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setObjectName("errorNotice")
        layout.addWidget(self.error)
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
            self.result.setPlainText("\n\n".join(reversed(history)))
            self.copy.setEnabled(True)
            self.error.clear()
        except ValueError as error:
            self.error.setText(str(error))
