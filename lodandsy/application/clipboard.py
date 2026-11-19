from PySide6.QtCore import QMimeData, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication


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

    def copy(self, text, *, html=None):
        self._timer.stop()
        self._text, self._remaining = text, 5
        self._html = html
        self._attempt()

    def _attempt(self):
        if self._html is None:
            self.clipboard.setText(self._text)
        else:
            data = QMimeData()
            data.setText(self._text)
            data.setHtml(self._html)
            self.clipboard.setMimeData(data)
        if self.clipboard.text() == self._text:
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
