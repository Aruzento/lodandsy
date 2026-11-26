"""A transient assortment of current-project Item UUIDs and live prices."""

from dataclasses import asdict
from random import Random

from lodandsy.domain.treasure import ShopParameters, ShopResult, generate_shop
from lodandsy.ui.treasure_widgets import ShopWidget


class ShopController:
    key = "tool:shop"

    def __init__(self, windows, project, settings, catalogue, lookup, open_item, *, rng=None):
        self.windows, self.project, self.settings = windows, project, settings
        self.catalogue, self.lookup, self.open_item = catalogue, lookup, open_item
        self.rng = rng if rng is not None else Random()
        self.parameters, self.result = ShopParameters(), None

    def open(self):
        if self.project() is None:
            return None
        window = self.windows.find_window(self.key)
        if window is not None:
            return self.windows.focus_window(self.key)
        window = self.windows.open_window(
            self.key, "Магазин", lambda: ShopWidget(
                self.settings(), self.parameters, self.generate, self.open_item
            ),
        )
        window.closed.connect(lambda closed: self._read_inputs(closed.widget()))
        self.refresh()
        return window

    def generate(self, parameters):
        self.parameters = parameters
        self.result = generate_shop(self.catalogue(), parameters, self.rng)
        self.refresh()
        return self.result

    def refresh(self, *_args):
        window = self.windows.find_window(self.key)
        if window is None:
            return
        currency = self.settings().currency
        rows, status = [], ""
        if self.result is not None:
            unavailable, unpriced, total = 0, 0, 0
            for key in self.result.item_ids:
                item = self.lookup(key)
                if item is None:
                    unavailable += 1
                    rows.append((key, (f"Предмет недоступен ({key[:8]})", "—", "—"), False))
                    continue
                if item.price is not None:
                    total += currency.value(item.price)
                else:
                    unpriced += 1
                weight = "—" if item.weight is None else f"{item.weight:.8g} фн."
                rows.append((key, (item.title, currency.price_text(item.price), weight), True))
            status = f"Позиций: {len(rows) - unavailable}"
            if self.result.available < self.result.requested:
                status += (
                    f" · При подборе доступно {self.result.available} из {self.result.requested}"
                )
            if unavailable:
                status += f" · Недоступно: {unavailable}"
            if unpriced:
                status += f" · Без цены: {unpriced}"
            if len(rows) > unavailable + unpriced:
                label = "Сумма известных цен" if unavailable or unpriced else "Итого"
                status += f" · {label}: {currency.total_text(total)}"
        view = window.widget()
        view.set_settings(self.settings())
        view.render(rows, status)

    def item_changed(self, key, fields):
        if fields & {"title", "weight", "cost"}:
            self.items_deleted((key,))

    def items_deleted(self, keys):
        if self.result is not None and set(self.result.item_ids).intersection(keys):
            self.refresh()

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
        }

    def restore(self, data):
        if not isinstance(data, dict) or data.get("version") != 1:
            return
        try:
            parameters = ShopParameters(**data["parameters"])
            raw = data["result"]
            result = ShopResult(tuple(raw["item_ids"]), raw["requested"], raw["available"]) if (
                raw is not None
            ) else None
        except (TypeError, KeyError, ValueError, RecursionError):
            return
        self.parameters, self.result = parameters, result

    def reset(self):
        self.windows.close_window(self.key)
        self.parameters, self.result = ShopParameters(), None
