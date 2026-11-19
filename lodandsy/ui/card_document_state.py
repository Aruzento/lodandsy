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
        self.view_preset = "sans"
        self.text_scale = 100

    def capture(self, editor: CardEditorWidget) -> None:
        cursor = editor.text_edit.textCursor()
        self.position, self.anchor = cursor.position(), cursor.anchor()
        self.vertical_scroll = editor.text_edit.verticalScrollBar().value()
        self.horizontal_scroll = editor.text_edit.horizontalScrollBar().value()
        self.mode = editor.mode_combo.currentIndex()
        self.splitter_sizes = editor.splitter.sizes()
        self.preview_scroll = editor.preview.verticalScrollBar().value()
        self.view_preset = editor.format_toolbar.view_preset.currentData()
        self.text_scale = editor.format_toolbar.scale.value()

    def ui_values(self):
        return {name: getattr(self, name) for name in [
            "position", "anchor", "vertical_scroll", "horizontal_scroll", "preview_scroll",
            "mode", "splitter_sizes", "view_preset", "text_scale",
        ]}

    def load_ui_values(self, values):
        for name in ["position", "anchor", "vertical_scroll", "horizontal_scroll",
                     "preview_scroll"]:
            value = values.get(name)
            if type(value) is int and 0 <= value <= 2_147_483_647:
                setattr(self, name, value)
        if values.get("mode") in [0, 1, 2]:
            self.mode = values["mode"]
        preset = values.get("view_preset")
        if isinstance(preset, str) and preset in {"sans", "serif", "mono"}:
            self.view_preset = preset
        scale = values.get("text_scale")
        if type(scale) is int and 75 <= scale <= 200:
            self.text_scale = scale
        sizes = values.get("splitter_sizes", [])
        if (isinstance(sizes, list)
                and all(type(n) is int and 0 <= n <= 2_147_483_647 for n in sizes)):
            self.splitter_sizes = sizes[:2]

    def restore(self, editor: CardEditorWidget) -> None:
        editor.format_toolbar.restore_preferences(self.view_preset, self.text_scale)
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
