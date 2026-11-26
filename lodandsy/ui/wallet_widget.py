"""Compact native wallet display and guarded whole-wallet edit."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lodandsy.domain.currency import CoinAmount, parse_coins


class WalletWidget(QWidget):
    def __init__(self, currency, document, update, parent=None):
        super().__init__(parent)
        self.currency = currency
        self.document = document
        self.update_wallet = update
        self.rows = QTreeWidget()
        self.rows.setAccessibleName("Номиналы кошелька")
        self.rows.setRootIsDecorated(False)
        self.rows.setHeaderHidden(True)
        self.rows.setColumnCount(2)
        self.rows.setMaximumHeight(132)
        self.rows.setUniformRowHeights(True)
        self.rows.header().setStretchLastSection(False)
        self.total = QLabel()
        self.total.setTextFormat(Qt.TextFormat.PlainText)
        self.edit_button = QPushButton("Изменить…")
        self.edit_button.setAccessibleName("Изменить кошелёк")
        self.edit_button.clicked.connect(self._edit)
        heading = QHBoxLayout()
        heading.addWidget(QLabel("Кошелёк"))
        heading.addWidget(self.total, 1)
        heading.addWidget(self.edit_button)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(heading)
        outer.addWidget(self.rows)
        self.refresh()

    def refresh(self):
        from PySide6.QtWidgets import QHeaderView

        currency, wallet = self.currency(), self.document().wallet
        counts = {coin.denomination_id: coin.count for coin in wallet}
        self.rows.clear()
        for denomination in currency.denominations:
            row = QTreeWidgetItem(self.rows, (
                f"{denomination.name} ({denomination.abbreviation})",
                str(counts.get(denomination.id, 0)),
            ))
            row.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header = self.rows.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.total.setText(currency.total_text(sum(currency.value(coin) for coin in wallet)))

    def _edit(self):
        document, currency = self.document(), self.currency()
        counts = {coin.denomination_id: coin.count for coin in document.wallet}
        dialog = QDialog(self)
        dialog.setWindowTitle("Кошелёк инвентаря")
        dialog.resize(360, min(480, 110 + len(currency.denominations) * 36))
        outer = QVBoxLayout(dialog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        fields = QFormLayout(content)
        edits = []
        for denomination in currency.denominations:
            edit = QLineEdit(str(counts.get(denomination.id, 0)))
            edit.setMaxLength(10)
            fields.addRow(f"{denomination.name} ({denomination.abbreviation})", edit)
            edits.append((denomination.id, edit))
        scroll.setWidget(content)
        outer.addWidget(scroll)
        error = QLabel()
        error.setWordWrap(True)
        error.setTextFormat(Qt.TextFormat.PlainText)
        outer.addWidget(error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        outer.addWidget(buttons)

        def save():
            try:
                if currency != self.currency():
                    raise ValueError("Система валют изменилась. Откройте кошелёк заново.")
                wallet = tuple(
                    coin for key, edit in edits
                    if (coin := CoinAmount(key, parse_coins(edit.text()))).count
                )
                self.update_wallet(wallet, expected=document.wallet)
            except ValueError as failure:
                error.setText(str(failure))
                return
            dialog.accept()

        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        dialog.exec()
        dialog.deleteLater()
