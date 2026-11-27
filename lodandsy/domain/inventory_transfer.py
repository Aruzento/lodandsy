from dataclasses import dataclass

from lodandsy.domain.currency import MAX_DENOMINATIONS, CoinAmount
from lodandsy.domain.module_values import validate_id

MAX_TRANSFER_ROWS = 500
MAX_ITEM_COUNT = 1_000_000_000


@dataclass(frozen=True, slots=True)
class ItemStack:
    item_id: str
    count: int

    def __post_init__(self):
        validate_id(self.item_id)
        if type(self.count) is not int or not 1 <= self.count <= MAX_ITEM_COUNT:
            raise ValueError("Количество предметов должно быть целым числом от 1 до 1 000 000 000")


@dataclass(frozen=True, slots=True)
class InventoryTransfer:
    project_id: str
    items: tuple[ItemStack, ...] = ()
    coins: tuple[CoinAmount, ...] = ()

    def __post_init__(self):
        validate_id(self.project_id)
        if (
            type(self.items) is not tuple or len(self.items) > MAX_TRANSFER_ROWS
            or any(type(item) is not ItemStack for item in self.items)
            or type(self.coins) is not tuple or len(self.coins) > MAX_DENOMINATIONS
            or any(type(coin) is not CoinAmount or coin.count == 0 for coin in self.coins)
            or not (self.items or self.coins)
        ):
            raise ValueError("Некорректный набор для вставки в инвентарь")
