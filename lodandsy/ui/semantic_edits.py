"""Native text controls: buffers while typing, commit at action boundaries, Escape cancels."""

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit


class SemanticLineEdit(QLineEdit):
    edit_started = Signal()
    buffer_changed = Signal(str)
    commit_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.editing = False
        self.textEdited.connect(self._edited)
        self.editingFinished.connect(self.finish)

    def _begin(self):
        if not self.editing:
            self.editing = True
            self.edit_started.emit()

    def focusInEvent(self, event):
        self._begin()
        super().focusInEvent(event)

    def _edited(self, text):
        self._begin()
        self.buffer_changed.emit(text)

    def finish(self):
        self._begin()
        self.buffer_changed.emit(self.text())
        self.editing = False
        self.commit_requested.emit(self.text())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.editing = False
            self.cancel_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def set_value(self, text, *, force=False):
        if self.editing and self.hasFocus() and not force:
            return
        if force:
            self.editing = False
        if self.text() != text:
            blocker = QSignalBlocker(self)
            self.setText(text)
            del blocker


class SemanticPlainTextEdit(QPlainTextEdit):
    edit_started = Signal()
    buffer_changed = Signal(str)
    commit_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.editing = False
        self.textChanged.connect(self._edited)

    def _begin(self):
        if not self.editing:
            self.editing = True
            self.edit_started.emit()

    def focusInEvent(self, event):
        self._begin()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.finish()
        super().focusOutEvent(event)

    def _edited(self):
        self._begin()
        self.buffer_changed.emit(self.toPlainText())

    def finish(self):
        self._begin()
        self.buffer_changed.emit(self.toPlainText())
        self.editing = False
        self.commit_requested.emit(self.toPlainText())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.editing = False
            self.cancel_requested.emit()
            event.accept()
            return
        if (
            event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.finish()
            event.accept()
            return
        super().keyPressEvent(event)

    def set_value(self, text, *, force=False):
        if self.editing and self.hasFocus() and not force:
            return
        if force:
            self.editing = False
        if self.toPlainText() != text:
            blocker = QSignalBlocker(self)
            self.setPlainText(text)
            del blocker
