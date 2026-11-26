"""Resolved equipment facts, independent of inventory storage and presentation."""

import math
from dataclasses import dataclass

EQUIPMENT_KINDS = ("item", "armor", "shield")
ARMOR_CATEGORIES = ("light", "medium", "heavy")


@dataclass(frozen=True, slots=True)
class EquipmentEntry:
    row_id: str
    item_id: str
    label: str
    kind: str
    armor_category: str | None = None
    armor_ac: int | float | None = None
    shield_bonus: int | float | None = None

    def __post_init__(self):
        if self.kind not in EQUIPMENT_KINDS:
            raise ValueError("Неизвестная категория экипировки")
        if self.armor_category is not None and self.armor_category not in ARMOR_CATEGORIES:
            raise ValueError("Неизвестная категория доспеха")
        for value in (self.armor_ac, self.shield_bonus):
            if value is not None and (
                type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1e9
            ):
                raise ValueError("КД и бонус щита должны быть конечными неотрицательными числами")


@dataclass(frozen=True, slots=True)
class EquipmentFacts:
    armor_type: str = "none"
    armor_base: int | float | None = 10
    shield: bool = False
    shield_bonus: int | float = 0
    armor: EquipmentEntry | None = None
    shield_item: EquipmentEntry | None = None
    diagnostic: str = ""
    conflicts: tuple[str, ...] = ()


def resolve_equipment(entries, *, missing=()):
    """Entries are already active; quantity never multiplies armor or shield."""
    entries = tuple(entries)
    if any(not isinstance(entry, EquipmentEntry) for entry in entries):
        raise ValueError("Некорректные факты экипировки")
    armor = tuple(entry for entry in entries if entry.kind == "armor")
    shields = tuple(entry for entry in entries if entry.kind == "shield")
    conflicts = tuple(
        entry.row_id for group in (armor, shields) if len(group) > 1 for entry in group
    )
    if conflicts:
        return EquipmentFacts(
            diagnostic="Надето несколько доспехов или щитов. Оставьте по одному.",
            conflicts=conflicts,
        )
    if missing:
        return EquipmentFacts(diagnostic="Активный предмет недоступен: " + ", ".join(missing))
    selected = armor[0] if armor else None
    shield = shields[0] if shields else None
    if selected and (
        selected.armor_category not in {"light", "medium", "heavy"} or selected.armor_ac is None
    ):
        return EquipmentFacts(
            armor_type=selected.armor_category or "none",
            armor_base=selected.armor_ac,
            armor=selected,
            shield_item=shield,
            diagnostic="Для надетого доспеха задайте категорию и базовый КД",
        )
    return EquipmentFacts(
        armor_type=selected.armor_category if selected else "none",
        armor_base=selected.armor_ac if selected else 10,
        shield=shield is not None,
        shield_bonus=(2 if shield.shield_bonus is None else shield.shield_bonus) if shield else 0,
        armor=selected,
        shield_item=shield,
    )
