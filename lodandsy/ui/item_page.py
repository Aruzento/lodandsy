"""Item properties and modifiers share a compact native page."""

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.domain.currency import CoinAmount
from lodandsy.domain.project_settings import ProjectSettings
from lodandsy.ui.card_fields import CardFieldsForm
from lodandsy.ui.conflict_bar import ConflictBar
from lodandsy.ui.modifier_editor import ModifierEditor, modifier_summary


class ItemPage(QWidget):
    price_started = Signal()
    price_committed = Signal(str)
    price_cancelled = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 12)
        self.properties = CardFieldsForm(groups=False)
        layout.addWidget(self.properties)
        self.settings = ProjectSettings
        self.category = QComboBox()
        self.category.setObjectName("field_item_category")
        self.category.currentIndexChanged.connect(self._category_changed)
        self.price = QPushButton()
        self.price.setObjectName("field_cost")
        self.price.clicked.connect(self._edit_price)
        commerce = QFormLayout()
        commerce.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        commerce.addRow("Категория", self.category)
        commerce.addRow("Стоимость", self.price)
        layout.addLayout(commerce)
        self._price_value, self._price_draft = None, None
        self.modifiers = ModifierEditor()
        layout.addWidget(self.modifiers, 1)
        self.conflicts = ConflictBar()
        self.conflicts.display_value = self._summary
        layout.addWidget(self.conflicts)

    def set_card(self, card, drafts, active):
        self.properties.set_card(
            card,
            (
                "equipment_kind",
                "armor_category",
                "armor_ac",
                "shield_bonus",
                "rarity",
                "weight",
                "loot_enabled",
            ),
            drafts,
        )
        kind = card.value("equipment_kind")
        for key in ("armor_category", "armor_ac"):
            self.properties.set_field_visible(key, kind == "armor")
        self.properties.set_field_visible("shield_bonus", kind == "shield")
        settings = self.settings()
        with QSignalBlocker(self.category):
            choices = (("Без категории", None), *((c.name, c.id) for c in settings.categories))
            if choices != getattr(self, "_category_choices", None):
                self._category_choices = choices
                self.category.clear()
                for label, key in choices:
                    self.category.addItem(label, key)
            self.category.setCurrentIndex(self.category.findData(card.value("item_category")))
        self._price_value = card.value("cost")
        self._price_draft = drafts.get((card.id, "cost"))
        self.price.setText(
            "Исправить цену…" if self._price_draft is not None
            else settings.currency.price_text(self._price_value)
        )
        self.modifiers.set_value(
            card.value("modifiers"),
            raw=drafts.get((card.id, "modifiers")),
            active=active("modifiers"),
        )

    def _category_changed(self):
        self.properties.edited.emit({"item_category": self.category.currentData()})

    def _edit_price(self):
        currency = self.settings().currency
        current = self._price_value
        dialog = QDialog(self)
        dialog.setWindowTitle("Стоимость предмета")
        form = QFormLayout(dialog)
        amount = QLineEdit()
        amount.setMaxLength(10)
        amount.setPlaceholderText("Пусто — цена не задана")
        denomination = QComboBox()
        for coin in currency.denominations:
            denomination.addItem(f"{coin.name} ({coin.abbreviation})", coin.id)
        count, key = (str(current.count), current.denomination_id) if current else (
            "", currency.base_id
        )
        if self._price_draft is not None:
            count, _, key = self._price_draft.partition("@")
        amount.setText(count)
        index = denomination.findData(key)
        base_index = denomination.findData(currency.base_id)
        denomination.setCurrentIndex(index if index >= 0 else base_index)
        form.addRow("Количество монет", amount)
        form.addRow("Номинал", denomination)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        amount.setFocus()
        self.price_started.emit()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            value = amount.text().strip()
            self.price_committed.emit(f"{value}@{denomination.currentData()}" if value else "")
        else:
            self.price_cancelled.emit()
        dialog.deleteLater()

    def _summary(self, value):
        import json
        from dataclasses import asdict

        from lodandsy.domain.modifiers import Modifier

        try:
            if isinstance(value, CoinAmount):
                return self.settings().currency.price_text(value)
            if isinstance(value, str) and "@" in value:
                return self.settings().currency.price_text(CoinAmount.from_text(value))
            if isinstance(value, str):
                value = json.loads(value)
            if isinstance(value, (tuple, list)):
                return "; ".join(
                    modifier_summary(asdict(v) if isinstance(v, Modifier) else v) for v in value
                )
        except ValueError, TypeError, AttributeError:
            return str(value)
        return str(value)
