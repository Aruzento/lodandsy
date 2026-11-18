from PySide6.QtCore import QObject
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QPlainTextDocumentLayout

from lodandsy.ui.card_editor import CardEditorWidget


class CardDocumentState:
    """Session-local editing state; world content remains in CardCollection."""

    def __init__(self, content: str, parent: QObject) -> None:
        self.document = QTextDocument(parent)
        self.document.setDocumentLayout(QPlainTextDocumentLayout(self.document))
        self.document.setPlainText(content)
        self.position = 0
        self.anchor = 0
        self.vertical_scroll = 0
        self.horizontal_scroll = 0
        self.mode = 0
        self.splitter_sizes: list[int] = []
        self.preview_scroll = 0

    def capture(self, editor: CardEditorWidget) -> None:
        cursor = editor.text_edit.textCursor()
        self.position, self.anchor = cursor.position(), cursor.anchor()
        self.vertical_scroll = editor.text_edit.verticalScrollBar().value()
        self.horizontal_scroll = editor.text_edit.horizontalScrollBar().value()
        self.mode = editor.mode_combo.currentIndex()
        self.splitter_sizes = editor.splitter.sizes()
        self.preview_scroll = editor.preview.verticalScrollBar().value()

    def restore(self, editor: CardEditorWidget) -> None:
        editor.mode_combo.setCurrentIndex(self.mode)
        if self.splitter_sizes:
            editor.splitter.setSizes(self.splitter_sizes)
        cursor = editor.text_edit.textCursor()
        limit = self.document.characterCount() - 1
        cursor.setPosition(min(self.anchor, limit))
        cursor.setPosition(min(self.position, limit), QTextCursor.MoveMode.KeepAnchor)
        editor.text_edit.setTextCursor(cursor)
        editor.text_edit.verticalScrollBar().setValue(self.vertical_scroll)
        editor.text_edit.horizontalScrollBar().setValue(self.horizontal_scroll)
        editor.preview.verticalScrollBar().setValue(self.preview_scroll)

    def sync_content(self, content: str) -> None:
        if self.document.toPlainText() == content:
            return
        cursor = QTextCursor(self.document)
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(content)
        cursor.endEditBlock()
