"""Exact currency rates and the rules for changing a project's denominations."""

import re
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from lodandsy.domain.module_values import validate_id, validate_title

RATE_SCALE = 100_000
MAX_RATE_UNITS = 1_000_000 * RATE_SCALE
MAX_DENOMINATIONS = 64
MAX_COINS = 1_000_000_000
STANDARD = "dnd_5e_2014"
CUSTOM = "custom"


def parse_rate(text: str) -> int:
    """Convert a decimal input into integer hundred-thousandths of the base."""
    units = parse_base_units(text)
    if not 1 <= units <= MAX_RATE_UNITS:
        raise ValueError("Курс должен быть от 0,00001 до 1 000 000")
    return units


def parse_base_units(text: str) -> int:
    text = text.strip().replace(",", ".")
    if not re.fullmatch(r"[0-9]{1,18}(?:\.[0-9]{1,5})?", text):
        raise ValueError("Введите число с точностью до пяти знаков после запятой")
    whole, _, fraction = text.partition(".")
    return int(whole) * RATE_SCALE + int(fraction.ljust(5, "0"))


def format_rate(units: int) -> str:
    whole, fraction = divmod(units, RATE_SCALE)
    return f"{whole},{fraction:05d}".rstrip("0").rstrip(",")


def parse_coins(text):
    if not re.fullmatch(r"[0-9]{1,10}", text.strip()):
        raise ValueError("Введите целое количество монет от 0 до 1 000 000 000")
    return int(text)


@dataclass(frozen=True, slots=True)
class CoinAmount:
    denomination_id: str
    count: int

    def __post_init__(self):
        validate_id(self.denomination_id)
        if type(self.count) is not int or not 0 <= self.count <= MAX_COINS:
            raise ValueError("Допустимо от 0 до 1 000 000 000 монет одного номинала")

    def to_text(self):
        return f"{self.count}@{self.denomination_id}"

    @classmethod
    def from_text(cls, text):
        count, _, denomination = text.partition("@")
        return cls(denomination, parse_coins(count))


def validate_wallet(wallet):
    if (
        type(wallet) is not tuple or len(wallet) > MAX_DENOMINATIONS
        or any(type(coin) is not CoinAmount or not coin.count for coin in wallet)
        or len({coin.denomination_id for coin in wallet}) != len(wallet)
    ):
        raise ValueError("Некорректный кошелёк")


@dataclass(frozen=True, slots=True)
class Denomination:
    id: str
    name: str
    abbreviation: str
    rate_units: int

    def __post_init__(self):
        validate_id(self.id)
        for key, maximum in (("name", 80), ("abbreviation", 12)):
            value = validate_title(getattr(self, key))
            if len(value) > maximum or any(ord(char) < 32 for char in value):
                raise ValueError("Слишком длинное или некорректное обозначение номинала")
            object.__setattr__(self, key, value)
        if type(self.rate_units) is not int or not 1 <= self.rate_units <= MAX_RATE_UNITS:
            raise ValueError("Курс должен быть от 0,00001 до 1 000 000")


_STANDARD_DENOMINATIONS = tuple(
    Denomination(str(uuid5(NAMESPACE_URL, f"lodandsy://currency/5e14/{key}")), name, label, rate)
    for key, name, label, rate in (
        ("pp", "Платиновая монета", "пм", 10 * RATE_SCALE),
        ("gp", "Золотая монета", "зм", RATE_SCALE),
        ("ep", "Электрумовая монета", "эм", RATE_SCALE // 2),
        ("sp", "Серебряная монета", "см", RATE_SCALE // 10),
        ("cp", "Медная монета", "мм", RATE_SCALE // 100),
    )
)
_STANDARD_BASE_ID = _STANDARD_DENOMINATIONS[1].id
_STANDARD_IDS = frozenset(denom.id for denom in _STANDARD_DENOMINATIONS)


@dataclass(frozen=True, slots=True)
class CurrencySystem:
    kind: str = STANDARD
    base_id: str = _STANDARD_BASE_ID
    denominations: tuple[Denomination, ...] = _STANDARD_DENOMINATIONS

    def __post_init__(self):
        if self.kind not in (STANDARD, CUSTOM):
            raise ValueError("Неизвестная система валют")
        if type(self.denominations) is not tuple or not 1 <= len(
            self.denominations
        ) <= MAX_DENOMINATIONS:
            raise ValueError(f"Допустимо от 1 до {MAX_DENOMINATIONS} номиналов")
        if any(type(denomination) is not Denomination for denomination in self.denominations):
            raise ValueError("Некорректный номинал")
        for attr in ("id", "name", "abbreviation"):
            if len({getattr(d, attr).casefold() for d in self.denominations}) != len(
                self.denominations
            ):
                raise ValueError("ID, названия и сокращения номиналов должны быть уникальными")
        if self.denomination(self.base_id).rate_units != RATE_SCALE:
            raise ValueError("Курс базовой единицы должен равняться 1")
        if self.kind == STANDARD:
            if self.denominations != _STANDARD_DENOMINATIONS or self.base_id != _STANDARD_BASE_ID:
                raise ValueError("Номиналы стандартной валютной системы фиксированы")
        elif _STANDARD_IDS.intersection(d.id for d in self.denominations):
            raise ValueError("Номиналы пользовательской системы должны иметь собственные ID")

    @property
    def base(self) -> Denomination:
        return self.denomination(self.base_id)

    def denomination(self, key: str) -> Denomination:
        for denomination in self.denominations:
            if denomination.id == key:
                return denomination
        raise ValueError("Неизвестный номинал")

    def value(self, amount: CoinAmount) -> int:
        return amount.count * self.denomination(amount.denomination_id).rate_units

    def price_text(self, amount: CoinAmount | None) -> str:
        if amount is None:
            return "Цена не задана"
        return f"{amount.count} {self.denomination(amount.denomination_id).abbreviation}"

    def total_text(self, units: int) -> str:
        return f"{format_rate(units)} {self.base.abbreviation}"

    def validate_change(self, candidate: CurrencySystem, used_ids):
        used_ids = set(used_ids)
        if not used_ids:
            return
        if self.kind != candidate.kind or self.base_id != candidate.base_id:
            raise ValueError("Систему и базовую единицу нельзя менять, пока используются номиналы")
        new_rates = {d.id: d.rate_units for d in candidate.denominations}
        for current in self.denominations:
            if current.id in used_ids and new_rates.get(current.id) != current.rate_units:
                raise ValueError(
                    f"Номинал «{current.name}» используется: курс и удаление заблокированы"
                )
