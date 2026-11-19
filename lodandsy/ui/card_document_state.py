from PySide6.QtGui import QTextCursor

from lodandsy.ui.rich_document import RichDocument


class CardDocumentState:
    """Session document and cursor/zoom state, independent of the editor window."""

    def __init__(self, content, parent):
        self.document = RichDocument(content, parent)
        self.position = self.anchor = self.vertical_scroll = self.horizontal_scroll = 0
        self.text_scale = 100
        self.images_connected = False

    def capture(self, editor):
        cursor = editor.text_edit.textCursor()
        self.position, self.anchor = cursor.position(), cursor.anchor()
        self.vertical_scroll = editor.text_edit.verticalScrollBar().value()
        self.horizontal_scroll = editor.text_edit.horizontalScrollBar().value()
        self.text_scale = editor.format_toolbar.scale.value()

    def ui_values(self):
        return {name: getattr(self, name) for name in (
            "position", "anchor", "vertical_scroll", "horizontal_scroll", "text_scale")}

    def load_ui_values(self, values):
        for name in ("position", "anchor", "vertical_scroll", "horizontal_scroll"):
            value = values.get(name)
            if type(value) is int and 0 <= value <= 2_147_483_647:
                setattr(self, name, value)
        scale = values.get("text_scale")
        if type(scale) is int and 75 <= scale <= 200:
            self.text_scale = scale

    def restore(self, editor):
        editor.format_toolbar.scale.setValue(self.text_scale)
        cursor = editor.text_edit.textCursor()
        limit = self.document.characterCount() - 1
        cursor.setPosition(min(self.anchor, limit))
        cursor.setPosition(min(self.position, limit), QTextCursor.MoveMode.KeepAnchor)
        editor.text_edit.setTextCursor(cursor)
        editor.text_edit.verticalScrollBar().setValue(self.vertical_scroll)
        editor.text_edit.horizontalScrollBar().setValue(self.horizontal_scroll)

    def sync_content(self, content):
        if self.document.canonical_content == content:
            return
        cursor = QTextCursor(self.document)
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.removeSelectedText()
        cursor.insertHtml(content)
        cursor.endEditBlock()
        self.document.canonical_content = content
