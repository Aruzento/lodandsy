"""Owns the current world's last loot result, without changing its entities."""

from dataclasses import asdict
from random import Random

from lodandsy.application.clipboard import clipboard_writer
from lodandsy.domain.currency import CoinAmount
from lodandsy.domain.inventory_transfer import InventoryTransfer, ItemStack
from lodandsy.domain.treasure import LootParameters, LootResult, generate_loot
from lodandsy.ui.treasure_widgets import LootWidget


class LootController:
    key = "tool:loot"

    def __init__(self, windows, project, settings, catalogue, lookup, open_item, *, rng=None):
        self.windows, self.project, self.settings = windows, project, settings
        self.catalogue, self.lookup, self.open_item = catalogue, lookup, open_item
        self.rng = rng if rng is not None else Random()
        self.parameters, self.result, self.locked = LootParameters(), None, set()

    def open(self):
        if self.project() is None:
            return None
        window = self.windows.find_window(self.key)
        if window is not None:
            return self.windows.focus_window(self.key)
        window = self.windows.open_window(
            self.key, "Генератор лута",
            lambda: LootWidget(
                self.settings(), self.parameters, self.generate, self.copy, self.pin, self.open_item
            ),
        )
        window.closed.connect(lambda closed: self._read_inputs(closed.widget()))
        self.refresh()
        return window

    def generate(self, parameters):
        self.parameters = parameters
        locked = tuple(stack for stack in self.result.items if stack.item_id in self.locked) if (
            self.result is not None
        ) else ()
        self.result = generate_loot(
            self.catalogue(), parameters, self.settings().currency, self.rng, locked=locked
        )
        self.refresh()
        return self.result

    def pin(self, row, pinned):
        if self.result is not None and 0 <= row < len(self.result.items):
            key = self.result.items[row].item_id
            if pinned:
                self.locked.add(key)
            else:
                self.locked.discard(key)

    def _presentation(self):
        if self.result is None:
            return (), "", "", False
        currency = self.settings().currency
        rows, issues, coin_lines = [], [], []
        total, count = 0, 0
        copyable = True
        for stack in self.result.items:
            item = self.lookup(stack.item_id)
            count += stack.count
            if item is None:
                caption = f"Предмет недоступен ({stack.item_id[:8]})"
                rows.append((stack.item_id, (caption, str(stack.count), "—", "—"), False))
                issues.append("есть удалённые или недоступные предметы")
                copyable = False
                continue
            value = currency.value(item.price) * stack.count if item.price is not None else None
            cost = currency.total_text(value) if value is not None else "Цена не задана"
            if value is None:
                issues.append("у части предметов отсутствует цена")
            else:
                total += value
            weight = "—" if item.weight is None else f"{item.weight * stack.count:.8g} фн."
            rows.append((stack.item_id, (item.title, str(stack.count), cost, weight), True))
        for coin in self.result.coins:
            try:
                caption = currency.price_text(coin)
                total += currency.value(coin)
            except ValueError:
                caption = f"Недоступный номинал ({coin.denomination_id[:8]}) × {coin.count}"
                issues.append("изменились номиналы валюты")
                copyable = False
            coin_lines.append(caption)
        status = f"Предметов: {count} · "
        if issues:
            status += "Итог неполный: " + ", ".join(dict.fromkeys(issues))
        elif total != self.result.total:
            status += f"Стоимость изменилась. Сейчас {currency.total_text(total)}"
        else:
            status += f"Итого: {currency.total_text(total)}"
        coins = "Монеты: " + ", ".join(coin_lines) if coin_lines else ""
        copyable = copyable and bool(rows or coins)
        return rows, status, coins, copyable

    def refresh(self, *_args):
        window = self.windows.find_window(self.key)
        if window is not None:
            rows, status, coins, copyable = self._presentation()
            view = window.widget()
            view.set_settings(self.settings())
            view.render(rows, self.locked, status, coins, copyable)

    def item_changed(self, key, fields):
        if fields & {"title", "weight", "cost"}:
            self.items_deleted((key,))

    def items_deleted(self, keys):
        if self.result is not None and {
            stack.item_id for stack in self.result.items
        }.intersection(keys):
            self.refresh()

    def copy(self):
        store, result = self.project(), self.result
        if store is None or result is None:
            return
        rows, status, coins, copyable = self._presentation()
        if not copyable:
            return
        lines = [
            f"{title} × {count} · {price} · {weight}"
            for _, (title, count, price, weight), _ in rows
        ]
        if coins:
            lines.append(coins)
        lines.append(status)
        text = "\n".join(lines)
        clipboard_writer().copy(
            text, inventory=InventoryTransfer(store.project_id, result.items, result.coins)
        )

    def _read_inputs(self, widget):
        try:
            self.parameters = widget.read_parameters()
        except ValueError:
            pass

    def capture(self):
        window = self.windows.find_window(self.key)
        if window is not None:
            self._read_inputs(window.widget())
        return {
            "version": 1,
            "parameters": asdict(self.parameters),
            "result": asdict(self.result) if self.result is not None else None,
            "locked": sorted(self.locked),
        }

    def restore(self, data):
        if not isinstance(data, dict) or data.get("version") != 1:
            return
        try:
            options = dict(data["parameters"])
            for key in ("categories", "budget", "money"):
                if options[key] is not None:
                    options[key] = tuple(options[key])
            parameters = LootParameters(**options)
            raw = data["result"]
            result = LootResult(
                tuple(ItemStack(**stack) for stack in raw["items"]),
                tuple(CoinAmount(**coin) for coin in raw["coins"]),
                raw["total"],
            ) if raw is not None else None
            item_ids = {stack.item_id for stack in result.items} if result is not None else set()
            locked = set(data["locked"]) & item_ids
        except (TypeError, KeyError, ValueError, RecursionError):
            return
        self.parameters, self.result, self.locked = parameters, result, locked

    def reset(self):
        self.windows.close_window(self.key)
        self.parameters, self.result, self.locked = LootParameters(), None, set()
