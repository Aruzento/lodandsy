from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from lodandsy.domain.module_values import validate_id, validate_title

MAX_CUSTOM_CATEGORIES = 64


@dataclass(frozen=True, slots=True)
class ItemCategory:
    id: str
    name: str

    def __post_init__(self):
        validate_id(self.id)
        name = validate_title(self.name)
        if len(name) > 80 or any(ord(char) < 32 for char in name):
            raise ValueError("Название категории должно содержать до 80 символов")
        object.__setattr__(self, "name", name)


STANDARD_CATEGORIES = tuple(
    ItemCategory(str(uuid5(NAMESPACE_URL, f"lodandsy://item-category/{key}")), name)
    for key, name in (
        ("weapons", "Оружие"),
        ("armor", "Доспехи и щиты"),
        ("gear", "Снаряжение"),
        ("consumables", "Расходники"),
        ("magic", "Магические предметы"),
        ("treasure", "Ценности"),
        ("other", "Прочее"),
    )
)


def validate_categories(custom):
    if (
        type(custom) is not tuple or len(custom) > MAX_CUSTOM_CATEGORIES
        or any(type(entry) is not ItemCategory for entry in custom)
    ):
        raise ValueError("Некорректный список категорий")
    all_categories = STANDARD_CATEGORIES + custom
    if (
        len({entry.id for entry in all_categories}) != len(all_categories)
        or len({entry.name.casefold() for entry in all_categories}) != len(all_categories)
    ):
        raise ValueError("Категории должны иметь уникальные названия и ID")
