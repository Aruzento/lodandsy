import json
from dataclasses import asdict

from lodandsy.domain.currency import CoinAmount, CurrencySystem, Denomination, validate_wallet
from lodandsy.domain.item_categories import ItemCategory

ECONOMY_VERSION = 1


def encode_economy(currency, categories=()):
    record = asdict(currency)
    record["categories"] = [asdict(value) for value in categories]
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def decode_economy(version, source):
    if version != ECONOMY_VERSION or not isinstance(source, str) or len(source) > 100_000:
        raise ValueError("Неподдерживаемый формат настроек экономики")
    record = json.loads(source)
    if not isinstance(record, dict) or set(record) != {
        "kind", "base_id", "denominations", "categories"
    }:
        raise ValueError("Некорректные настройки экономики")
    if not all(isinstance(record[key], list) for key in ("denominations", "categories")):
        raise ValueError("Некорректные номиналы или категории")
    denominations = tuple(Denomination(**value) for value in record["denominations"])
    categories = tuple(ItemCategory(**value) for value in record["categories"])
    return CurrencySystem(record["kind"], record["base_id"], denominations), categories


def encode_wallet(wallet):
    return json.dumps([asdict(amount) for amount in wallet], separators=(",", ":"))


def decode_wallet(source):
    if not isinstance(source, str) or len(source) > 10_000:
        raise ValueError("Некорректный кошелёк таблицы")
    values = json.loads(source)
    if not isinstance(values, list):
        raise ValueError("Некорректный кошелёк таблицы")
    wallet = tuple(CoinAmount(**value) for value in values)
    validate_wallet(wallet)
    return wallet
