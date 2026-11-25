"""Item properties and modifiers share a compact native page."""

from PySide6.QtWidgets import QVBoxLayout, QWidget

from lodandsy.ui.card_fields import CardFieldsForm
from lodandsy.ui.conflict_bar import ConflictBar
from lodandsy.ui.modifier_editor import ModifierEditor, modifier_summary


class ItemPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 12)
        self.properties = CardFieldsForm(groups=False)
        layout.addWidget(self.properties)
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
                "cost",
            ),
            drafts,
        )
        kind = card.value("equipment_kind")
        for key in ("armor_category", "armor_ac"):
            self.properties.set_field_visible(key, kind == "armor")
        self.properties.set_field_visible("shield_bonus", kind == "shield")
        self.modifiers.set_value(
            card.value("modifiers"),
            raw=drafts.get((card.id, "modifiers")),
            active=active("modifiers"),
        )

    @staticmethod
    def _summary(value):
        import json
        from dataclasses import asdict

        from lodandsy.domain.modifiers import Modifier

        try:
            if isinstance(value, str):
                value = json.loads(value)
            if isinstance(value, (tuple, list)):
                return "; ".join(
                    modifier_summary(asdict(v) if isinstance(v, Modifier) else v) for v in value
                )
        except ValueError, TypeError, AttributeError:
            return "Ошибочный ввод модификаторов"
        return str(value)
