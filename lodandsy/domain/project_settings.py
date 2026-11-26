from dataclasses import dataclass, field

from lodandsy.domain.currency import CurrencySystem
from lodandsy.domain.item_categories import STANDARD_CATEGORIES, ItemCategory, validate_categories


@dataclass(frozen=True, slots=True)
class ProjectSettings:
    rules: object | None = None
    currency: CurrencySystem = field(default_factory=CurrencySystem)
    custom_categories: tuple[ItemCategory, ...] = ()

    def __post_init__(self):
        if type(self.currency) is not CurrencySystem:
            raise ValueError("Некорректная система валют")
        validate_categories(self.custom_categories)

    @property
    def categories(self):
        return STANDARD_CATEGORIES + self.custom_categories
