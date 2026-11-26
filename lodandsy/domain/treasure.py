"""Pure Item catalogue projections and bounded exact loot generation."""

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from math import gcd

from lodandsy.domain.currency import MAX_COINS, RATE_SCALE, CoinAmount, validate_wallet
from lodandsy.domain.inventory_transfer import ItemStack
from lodandsy.domain.module_values import validate_id

MAX_LOOT_COUNT = 100
MAX_SHOP_COUNT = 500
SHOP_ALL = "all"
MAX_BUDGET = 10**17 * RATE_SCALE
SEARCH_STEPS = 30_000


@dataclass(frozen=True, slots=True)
class CatalogItem:
    id: str
    title: str
    category_id: str | None
    price: CoinAmount | None
    weight: int | float | None
    loot_enabled: bool


@dataclass(frozen=True, slots=True)
class LootParameters:
    minimum: int = 1
    maximum: int = 5
    budget: tuple[int, int] = (0, 100 * RATE_SCALE)
    categories: tuple[str | None, ...] = ()
    money: tuple[int, int] | None = None

    def __post_init__(self):
        if (
            type(self.minimum) is not int or type(self.maximum) is not int
            or not 0 <= self.minimum <= self.maximum <= MAX_LOOT_COUNT
        ):
            raise ValueError(f"Диапазон количества должен быть от 0 до {MAX_LOOT_COUNT}")
        if type(self.categories) is not tuple or len(self.categories) > 80:
            raise ValueError("Некорректный список категорий")
        for category in self.categories:
            if category is not None:
                validate_id(category)
        ranges = (self.budget,) if self.money is None else (self.budget, self.money)
        for bounds in ranges:
            if (
                type(bounds) is not tuple or len(bounds) != 2
                or any(type(value) is not int for value in bounds)
                or not 0 <= bounds[0] <= bounds[1] <= MAX_BUDGET
            ):
                raise ValueError("Некорректный диапазон стоимости")
        if self.money is not None and self.money[0] > self.budget[1]:
            raise ValueError("Минимум монет превышает общий бюджет")


@dataclass(frozen=True, slots=True)
class LootResult:
    items: tuple[ItemStack, ...]
    coins: tuple[CoinAmount, ...]
    total: int

    def __post_init__(self):
        if (
            type(self.items) is not tuple or len(self.items) > MAX_LOOT_COUNT
            or any(type(stack) is not ItemStack for stack in self.items)
            or sum(stack.count for stack in self.items) > MAX_LOOT_COUNT
            or len({stack.item_id for stack in self.items}) != len(self.items)
            or type(self.total) is not int or not 0 <= self.total <= MAX_BUDGET
        ):
            raise ValueError("Некорректный результат генерации")
        validate_wallet(self.coins)


class LootUnreachable(ValueError):
    pass


class LootSearchExhausted(ValueError):
    pass


def generate_loot(catalogue, parameters, currency, rng, *, locked=(), max_steps=SEARCH_STEPS):
    """Search multisets with price bounds, sharing one budget with the coin solver."""
    categories = frozenset(parameters.categories)
    eligible = {
        item.id: item for item in catalogue
        if item.loot_enabled and (not categories or item.category_id in categories)
    }
    priced = {key: currency.value(item.price) for key, item in eligible.items() if item.price}
    if any(stack.item_id not in priced for stack in locked):
        raise LootUnreachable(
            "Закреплённый предмет недоступен, исключён фильтром или не имеет цены"
        )
    pinned = {stack.item_id: stack.count for stack in locked}
    pinned_count = sum(pinned.values())
    pinned_total = sum(priced[key] * count for key, count in pinned.items())
    low, high = parameters.budget
    money_low, money_high = parameters.money or (0, 0)
    if pinned_count > parameters.maximum or pinned_total + money_low > high:
        raise LootUnreachable("Закреплённые позиции превышают заданные пределы")
    pool = [(key, value) for key, value in priced.items() if key not in pinned]
    if not pool and parameters.minimum > pinned_count:
        if eligible and not priced:
            raise LootUnreachable("У подходящих предметов не указана цена")
        raise LootUnreachable("Нет подходящих предметов для незакреплённых позиций")

    rng.shuffle(pool)
    min_price, max_price = [0] * len(pool), [0] * len(pool)
    for index in reversed(range(len(pool))):
        price = pool[index][1]
        min_price[index] = min(min_price[index + 1], price) if index + 1 < len(pool) else price
        max_price[index] = max(max_price[index + 1], price) if index + 1 < len(pool) else price

    denoms = sorted(currency.denominations, key=lambda denom: -denom.rate_units)
    limits, divisors = [0] * (len(denoms) + 1), [0] * (len(denoms) + 1)
    for index in reversed(range(len(denoms))):
        rate = denoms[index].rate_units
        limits[index] = limits[index + 1] + MAX_COINS * rate
        divisors[index] = gcd(rate, divisors[index + 1])

    def step():
        nonlocal max_steps
        max_steps -= 1
        if max_steps < 0:
            raise LootSearchExhausted("Лимит поиска исчерпан. Расширьте диапазоны или повторите.")

    @lru_cache(maxsize=SEARCH_STEPS)
    def coins(index, least, most):
        step()
        least, most = max(least, 0), min(most, limits[index])
        if least > most:
            return None
        if not most or index == len(denoms):
            return ()
        divisor = divisors[index]
        if (least + divisor - 1) // divisor > most // divisor:
            return None
        denomination = denoms[index]
        rate = denomination.rate_units
        start = max(0, (least - limits[index + 1] + rate - 1) // rate)
        end = min(MAX_COINS, most // rate)
        if start > end:
            return None
        offset = rng.randint(start, end)
        for count in range(offset, end + 1):
            result = coin_tail(index, count, rate, least, most, denomination.id)
            if result is not None:
                return result
        for count in range(start, offset):
            result = coin_tail(index, count, rate, least, most, denomination.id)
            if result is not None:
                return result
        return None

    def coin_tail(index, count, rate, least, most, key):
        step()
        tail = coins(index + 1, least - count * rate, most - count * rate)
        if tail is None or not count:
            return tail
        return (CoinAmount(key, count), *tail)

    @lru_cache(maxsize=SEARCH_STEPS)
    def items(start, remaining, total):
        step()
        if remaining == 0:
            least = max(money_low, low - total)
            most = min(money_high, high - total)
            if parameters.money is None:
                return ((), ()) if least <= 0 <= most else None
            extra = coins(0, least, most)
            return ((), extra) if extra is not None else None
        if (
            start >= len(pool)
            or total + remaining * min_price[start] + money_low > high
            or total + remaining * max_price[start] + money_high < low
        ):
            return None
        for index in range(start, len(pool)):
            step()
            key, price = pool[index]
            result = items(index, remaining - 1, total + price)
            if result is not None:
                return (key, *result[0]), result[1]
        return None

    counts = list(range(max(0, parameters.minimum - pinned_count),
                        parameters.maximum - pinned_count + 1))
    rng.shuffle(counts)
    for count in counts:
        answer = items(0, count, pinned_total)
        if answer is not None:
            keys, wallet = answer
            quantities = Counter(pinned)
            quantities.update(keys)
            stacks = tuple(ItemStack(key, qty) for key, qty in quantities.items())
            total = sum(priced[key] * qty for key, qty in quantities.items())
            return LootResult(stacks, wallet, total + sum(currency.value(coin) for coin in wallet))
    raise LootUnreachable("Заданные диапазоны количества и стоимости недостижимы")


@dataclass(frozen=True, slots=True)
class ShopParameters:
    minimum: int = 20
    maximum: int = 50
    category: str | None = SHOP_ALL

    def __post_init__(self):
        if (
            type(self.minimum) is not int or type(self.maximum) is not int
            or not 1 <= self.minimum <= self.maximum <= MAX_SHOP_COUNT
        ):
            raise ValueError(f"Диапазон ассортимента должен быть от 1 до {MAX_SHOP_COUNT}")
        if self.category not in (None, SHOP_ALL):
            validate_id(self.category)


@dataclass(frozen=True, slots=True)
class ShopResult:
    item_ids: tuple[str, ...]
    requested: int
    available: int

    def __post_init__(self):
        if (
            type(self.requested) is not int or not 1 <= self.requested <= MAX_SHOP_COUNT
            or type(self.available) is not int or self.available < 0
            or type(self.item_ids) is not tuple
            or len(self.item_ids) != min(self.requested, self.available)
        ):
            raise ValueError("Некорректный ассортимент")
        for key in self.item_ids:
            validate_id(key)
        if len(set(self.item_ids)) != len(self.item_ids):
            raise ValueError("Предметы в ассортименте должны быть уникальны")


def generate_shop(catalogue, parameters, rng):
    candidates = list(dict.fromkeys(
        item.id for item in catalogue
        if parameters.category == SHOP_ALL or item.category_id == parameters.category
    ))
    requested = rng.randint(parameters.minimum, parameters.maximum)
    return ShopResult(
        tuple(rng.sample(candidates, min(requested, len(candidates)))), requested, len(candidates)
    )
