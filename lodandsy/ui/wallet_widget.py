"""Inline inventory wallet using the shared semantic edit lifecycle."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from lodandsy.ui.conflict_bar import ConflictBar
from lodandsy.ui.semantic_edits import SemanticLineEdit
from lodandsy.ui.theme import apply_role


class WalletWidget(QWidget):
    def __init__(self, currency, document, edits, parent=None):
        super().__init__(parent)
        self.currency, self.document, self.edits = currency, document, edits
        self.table_id = document().id
        self.controls, self.owners = {}, {}
        heading = QHBoxLayout()
        caption = QLabel("Кошелёк")
        apply_role(caption, "group")
        heading.addWidget(caption)
        heading.addStretch(1)
        self.total = QLabel()
        self.total.setTextFormat(Qt.TextFormat.PlainText)
        apply_role(self.total, "total")
        heading.addWidget(self.total)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rows = QWidget()
        self.grid = QGridLayout(self.rows)
        self.grid.setContentsMargins(0, 0, 4, 0)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(2)
        self.grid.setColumnStretch(0, 1)
        self.scroll.setWidget(self.rows)

        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        apply_role(self.error, "error")
        self.conflicts = ConflictBar(self)
        self.conflicts.resolve_requested.connect(self._resolve)
        self.discard = QPushButton("Восстановить сохранённое")
        self.discard.clicked.connect(self._discard_invalid)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        outer.addLayout(heading)
        for widget in (self.scroll, self.error, self.discard, self.conflicts):
            outer.addWidget(widget)
        self._denominations = ()
        self.edits.changed.connect(self._change)
        self.refresh()

    def _rebuild(self, denominations):
        self._denominations = denominations
        for control in self.controls.values():
            control.blockSignals(True)
        self.controls.clear()
        self.finish_edits()
        while self.grid.count():
            self.grid.takeAt(0).widget().deleteLater()
        for row, denomination in enumerate(denominations):
            key = self.table_id, denomination.id
            label = QLabel(f"{denomination.name} · {denomination.abbreviation}")
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setToolTip(label.text())
            label.setMinimumWidth(0)
            control = SemanticLineEdit()
            control.setAlignment(Qt.AlignmentFlag.AlignRight)
            control.setMaxLength(10)
            control.setFixedWidth(108)
            control.setAccessibleName(f"Количество · {denomination.name}")
            control.setToolTip("Enter или Tab сохраняет количество, Escape отменяет ввод")
            apply_role(control, "compact")
            label.setBuddy(control)
            control.edit_started.connect(lambda k=key: self._begin(k))
            control.buffer_changed.connect(lambda raw, k=key: self._buffer(k, raw))
            control.commit_requested.connect(lambda raw, k=key: self._commit(k, raw))
            control.cancel_requested.connect(lambda k=key: self._cancel(k))
            self.controls[key] = control
            self.grid.addWidget(label, row, 0)
            self.grid.addWidget(control, row, 1)
        self.scroll.setFixedHeight(max(30, min(len(denominations), 5) * 27))

    def refresh(self):
        currency, wallet = self.currency(), self.document().wallet
        if self._denominations != currency.denominations:
            self._rebuild(currency.denominations)
        counts = {coin.denomination_id: coin.count for coin in wallet}
        for key, control in self.controls.items():
            value = self.edits.drafts.get(key, str(counts.get(key[1], 0)))
            control.set_value(value, force=not self.edits.has(self.owners.get(key)))
            invalid = key in self.edits.errors
            if control.property("invalid") != invalid:
                control.setProperty("invalid", invalid)
                control.style().unpolish(control)
                control.style().polish(control)
        self.total.setText(currency.total_text(sum(currency.value(coin) for coin in wallet)))
        error = next((self.edits.errors[key] for key in self.controls if key in self.edits.errors),
                     "")
        self.error.setText(error)
        self.error.setVisible(bool(error))
        self.discard.setVisible(any(
            key in self.edits.errors and key not in self.edits.conflicts
            for key in self.controls
        ))
        self.conflicts.set_conflicts([
            (key, currency.denomination(key[1]).name, self.edits.drafts[key], issue.observed)
            for key, issue in self.edits.conflicts.items() if key in self.controls
        ])

    def _change(self, key):
        if key[0] == self.table_id:
            self.refresh()

    def _begin(self, key):
        if not self.edits.has(self.owners.get(key)):
            try:
                self.owners[key] = self.edits.begin(key)
            except ValueError:
                return

    def _buffer(self, key, raw):
        self._begin(key)
        self.edits.text(self.owners.get(key), raw)

    def _commit(self, key, raw):
        self._buffer(key, raw)
        self.edits.commit(self.owners.pop(key, None), finish=True)
        self.refresh()

    def _cancel(self, key):
        owner = self.owners.pop(key, None)
        self.edits.cancel(owner)
        self.refresh()

    def _resolve(self, key, mine):
        if key is not None:
            self.edits.resolve(key, mine=mine)

    def _discard_invalid(self):
        self.edits.discard_keys(
            key for key in self.controls
            if key in self.edits.errors and key not in self.edits.conflicts
        )

    def finish_edits(self):
        owners, self.owners = tuple(self.owners.values()), {}
        for owner in owners:
            self.edits.commit(owner, finish=True)
