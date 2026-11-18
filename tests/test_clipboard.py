from lodandsy.application.clipboard import ClipboardWriter


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
