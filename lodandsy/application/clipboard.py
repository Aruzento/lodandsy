import json
from dataclasses import asdict

from PySide6.QtCore import QMimeData, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from lodandsy.domain.currency import CoinAmount
from lodandsy.domain.inventory_transfer import InventoryTransfer, ItemStack

INVENTORY_MIME = "application/x-lodandsy-inventory+json"
INVENTORY_TRANSFER_VERSION = 1


def encode_inventory_transfer(transfer):
    data = asdict(transfer)
    data["version"] = INVENTORY_TRANSFER_VERSION
    return json.dumps(data, separators=(",", ":")).encode("utf-8")


def _unique_pairs(pairs):
    data = dict(pairs)
    if len(data) != len(pairs):
        raise ValueError("Повторяющееся поле буфера обмена")
    return data


def decode_inventory_transfer(source):
    try:
        if len(source) > 96_000:
            raise ValueError("Слишком большой набор")
        data = json.loads(source, object_pairs_hook=_unique_pairs)
        if type(data) is not dict or data.keys() != {"version", "project_id", "items", "coins"}:
            raise ValueError("Некорректные поля")
        if type(data["version"]) is not int or data["version"] != INVENTORY_TRANSFER_VERSION:
            raise ValueError("Неподдерживаемая версия")
        if type(data["items"]) is not list or type(data["coins"]) is not list:
            raise ValueError("Ожидается список предметов и монет")
        return InventoryTransfer(
            data["project_id"],
            tuple(ItemStack(**item) for item in data["items"]),
            tuple(CoinAmount(**coin) for coin in data["coins"]),
        )
    except (ValueError, TypeError, RecursionError) as error:
        raise ValueError(f"Некорректный набор инвентаря в буфере обмена. {error}") from error


class ClipboardWriter(QObject):
    message = Signal(str)

    def __init__(self, clipboard, parent=None):
        super().__init__(parent)
        self.clipboard = clipboard
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._attempt)
        self._text = ""
        self._remaining = 0

    def copy(self, text, *, html=None, inventory=None):
        self._timer.stop()
        self._text = text
        # Windows clipboard managers can hold the OLE clipboard past the text retry window.
        self._remaining = 25 if inventory is not None else 5
        self._html = html
        self._inventory = None if inventory is None else encode_inventory_transfer(inventory)
        self._attempt()

    def _attempt(self):
        if self._html is None and self._inventory is None:
            self.clipboard.setText(self._text)
        else:
            data = QMimeData()
            data.setText(self._text)
            if self._html is not None:
                data.setHtml(self._html)
            if self._inventory is not None:
                data.setData(INVENTORY_MIME, self._inventory)
            self.clipboard.setMimeData(data)
        if self._inventory is None:
            copied = self.clipboard.text() == self._text
        else:
            current = self.clipboard.mimeData()
            copied = (current is not None and bytes(current.data(INVENTORY_MIME)) == self._inventory
                      and current.text() == self._text)
        if copied:
            self.message.emit("Скопировано")
            return
        self._remaining -= 1
        if self._remaining:
            self._timer.start()
        else:
            self.message.emit("Не удалось скопировать: буфер обмена занят. Повторите команду.")


def clipboard_writer():
    app = QApplication.instance()
    if not hasattr(app, "_lodandsy_clipboard"):
        app._lodandsy_clipboard = ClipboardWriter(app.clipboard(), app)
    return app._lodandsy_clipboard


def copy_text(text):
    clipboard_writer().copy(text)
