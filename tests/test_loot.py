from random import Random
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from lodandsy.application.clipboard import (
    INVENTORY_MIME,
    clipboard_writer,
    decode_inventory_transfer,
)
from lodandsy.domain.currency import RATE_SCALE, CoinAmount, CurrencySystem
from lodandsy.domain.inventory_transfer import ItemStack
from lodandsy.domain.treasure import (
    CatalogItem,
    LootParameters,
    LootSearchExhausted,
    LootUnreachable,
    generate_loot,
)

pytest_plugins = ["tests.project_fixture"]


def test_equal_price_pool_produces_varied_multisets_without_banning_repeats():
    currency = CurrencySystem()
    price = CoinAmount(currency.base_id, 1)
    pool = tuple(CatalogItem(str(uuid4()), str(i), None, price, None, True) for i in range(10))
    params = LootParameters(5, 5, (5 * RATE_SCALE, 5 * RATE_SCALE))
    rng = Random(724)
    results = [generate_loot(pool, params, currency, rng) for _ in range(100)]
    assert len({frozenset(result.items) for result in results}) > 50
    assert sum(len(result.items) > 1 for result in results) > 90
    assert any(stack.count > 1 for result in results for stack in result.items)
    required = generate_loot(pool[:1], params, currency, Random(724))
    assert required.items == (ItemStack(pool[0].id, 5),)
    assert all(result.total == 5 * RATE_SCALE for result in results)


def test_loot_repeat_money_and_pin_are_exact():
    currency = CurrencySystem()
    rate = RATE_SCALE
    first = CatalogItem(str(uuid4()), "Сфера", None, CoinAmount(currency.base_id, 3), 0, True)
    other = CatalogItem(str(uuid4()), "Сапог", None, CoinAmount(currency.base_id, 2), 1, True)
    params = LootParameters(3, 3, (10 * rate, 10 * rate), money=(rate, rate))
    result = generate_loot((first, other), params, currency, Random(2))
    assert result.items == (ItemStack(first.id, 3),)
    assert result.total == 10 * rate and sum(currency.value(coin) for coin in result.coins) == rate
    pinned = (ItemStack(first.id, 1),)
    params = LootParameters(3, 3, (8 * rate, 8 * rate), money=(rate, rate))
    result = generate_loot((first, other), params, currency, Random(2), locked=pinned)
    assert result.items == (*pinned, ItemStack(other.id, 2))
    assert result.total == 8 * rate


def test_missing_zero_unreachable_and_exhausted_are_distinct():
    currency = CurrencySystem()
    zero = CatalogItem(str(uuid4()), "Камень", None, CoinAmount(currency.base_id, 0), None, True)
    unknown = CatalogItem(str(uuid4()), "Перстень", None, None, None, True)
    params = LootParameters(1, 1, (0, 0))
    assert generate_loot((zero, unknown), params, currency, Random(9)).items[0].item_id == zero.id
    with pytest.raises(LootUnreachable, match="цена"):
        generate_loot((unknown,), params, currency, Random(9))
    with pytest.raises(LootUnreachable, match="Нет подходящих"):
        generate_loot((), params, currency, Random(9))
    with pytest.raises(LootUnreachable, match="недостижимы"):
        generate_loot((), LootParameters(0, 0, (1, 1), money=(1, 1)), currency, Random(9))
    with pytest.raises(LootSearchExhausted, match="Лимит"):
        generate_loot((zero,), params, currency, Random(9), max_steps=1)


def test_native_loot_tool_restores_last_result_and_resolves_live_cards(project, tmp_path, qtbot):
    app, projects = project
    assert app.loot.open() is None
    root = tmp_path / "Мир лута"
    assert projects.create_project(root)
    item = app.create_card("Меч", card_type="item")
    base = app.economy.currency.base_id
    app.cards_service.update_card_fields(
        item.id, {"cost": CoinAmount(base, 1), "loot_enabled": True}
    )
    window = app.loot.open()
    assert app.loot.open() is window
    view = window.widget()
    view.count[0].setValue(2)
    view.count[1].setValue(2)
    serial = app.core.serial
    view.generate_button.click()
    assert app.core.serial == serial
    assert app.loot.result.items == (ItemStack(item.id, 2),)
    view.results.item(0, 4).setCheckState(Qt.CheckState.Checked)
    with qtbot.waitSignal(clipboard_writer().message, timeout=10000) as copy_result:
        view.copy_button.click()
    assert copy_result.args == ["Скопировано"]
    clipboard = QApplication.clipboard()
    mime = bytes(clipboard.mimeData().data(INVENTORY_MIME))
    transfer = decode_inventory_transfer(mime)
    assert transfer.items == app.loot.result.items
    assert transfer.project_id == projects.store.project_id
    assert projects.save_current()
    assert projects.create_project(tmp_path / "Иной мир", preserve_current=False)
    assert app.loot.result is None and app.window_manager.find_window(app.loot.key) is None
    projects.open_project(root)
    assert app.loot.parameters.minimum == 2 and app.loot.locked == {item.id}
    view = app.loot.open().widget()
    assert view.results.item(0, 4).checkState() == Qt.CheckState.Checked
    app.cards_service.update_card_fields(item.id, {"cost": CoinAmount(base, 3)})
    assert view.results.item(0, 2).text() == "6 зм"
    assert "Стоимость изменилась" in view.summary.text()
    app.actions.delete_entity(item.id)
    assert "недоступен" in view.results.item(0, 0).text()
    assert not view.copy_button.isEnabled()
    clipboard.clear()
