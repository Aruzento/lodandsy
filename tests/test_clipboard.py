from uuid import uuid4

from lodandsy.application.clipboard import (
    INVENTORY_MIME,
    ClipboardWriter,
    decode_inventory_transfer,
)
from lodandsy.domain.inventory_transfer import InventoryTransfer, ItemStack


class BusyClipboard:
    def __init__(self):
        self.busy = True
        self.value = ""

    def setText(self, text):
        if not self.busy:
            self.value = text

    def text(self):
        return self.value


def test_clipboard_retry_uses_latest_intent_and_reports_success(qtbot):
    clipboard = BusyClipboard()
    writer = ClipboardWriter(clipboard)
    messages = []
    writer.message.connect(messages.append)
    writer.copy("First")
    writer.copy("Latest")
    clipboard.busy = False
    qtbot.waitUntil(lambda: clipboard.value == "Latest")
    assert messages == ["Скопировано"]


def test_busy_clipboard_failure_is_visible_and_keeps_existing_content(qtbot):
    clipboard = BusyClipboard()
    clipboard.value = "Existing"
    writer = ClipboardWriter(clipboard)
    writer._timer.setInterval(1)
    messages = []
    writer.message.connect(messages.append)
    writer.copy("New")
    qtbot.waitUntil(lambda: bool(messages))
    assert "Не удалось" in messages[-1]
    assert clipboard.value == "Existing"


def test_typed_clipboard_retries_past_the_plain_text_window(qtbot):
    class BusyMimeClipboard:
        data = None
        attempts = 0

        def setMimeData(self, data):
            self.attempts += 1
            if self.attempts > 5:
                self.data = data

        def mimeData(self):
            return self.data

    clipboard = BusyMimeClipboard()
    writer = ClipboardWriter(clipboard)
    writer._timer.setInterval(1)
    payload = InventoryTransfer(str(uuid4()), (ItemStack(str(uuid4()), 2),))
    with qtbot.waitSignal(writer.message) as report:
        writer.copy("Зелье × 2", inventory=payload)
    assert report.args == ["Скопировано"]
    assert clipboard.attempts == 6
    assert decode_inventory_transfer(bytes(clipboard.data.data(INVENTORY_MIME))) == payload
