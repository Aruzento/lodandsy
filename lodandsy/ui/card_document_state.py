from PySide6.QtGui import QTextCursor

from lodandsy.ui.rich_document import RichDocument


class CardDocumentState:
    """Session document and cursor/zoom state, independent of the editor window."""

    def __init__(self, content, parent):
        self.parent = parent
        self.sections = {}
        self.section_preferences = {}
        self.active_section = "description"
        self.document = RichDocument(content, parent)
        self.position = self.anchor = self.vertical_scroll = self.horizontal_scroll = 0
        self.text_scale = 100
        self.images_connected = False

    def capture(self, editor):
        self.active_section = getattr(editor, "current_section", "description")
        target = self.section(self.active_section)
        target.capture_position(editor)

    def section(self, key, content=None):
        from lodandsy.domain.card import EMPTY_DOCUMENT

        if key == "description":
            return self
        if key not in self.sections:
            self.sections[key] = CardDocumentState(content or EMPTY_DOCUMENT, self.parent)
            self.sections[key].load_ui_values(self.section_preferences.get(key, {}))
        return self.sections[key]

    def documents(self):
        return (self.document, *(s.document for s in self.sections.values()))

    def delete(self):
        for document in self.documents():
            document.deleteLater()

    def capture_position(self, editor):
        cursor = editor.text_edit.textCursor()
        self.position, self.anchor = cursor.position(), cursor.anchor()
        self.vertical_scroll = editor.text_edit.verticalScrollBar().value()
        self.horizontal_scroll = editor.text_edit.horizontalScrollBar().value()
        self.text_scale = editor.format_toolbar.scale.value()
        self.document.release_images()

    def ui_values(self):
        values = self.position_values()
        values["active_section"] = self.active_section
        values["sections"] = {key: state.position_values() for key, state in self.sections.items()}
        return values

    def position_values(self):
        return {
            name: getattr(self, name)
            for name in ("position", "anchor", "vertical_scroll", "horizontal_scroll", "text_scale")
        }

    def load_ui_values(self, values):
        from lodandsy.domain.card_schema import FIELD_DEFINITIONS

        key = values.get("active_section", "description")
        if key in FIELD_DEFINITIONS and FIELD_DEFINITIONS[key].data_type == "richtext":
            self.active_section = key
        self.section_preferences = (
            values.get("sections", {}) if isinstance(values.get("sections"), dict) else {}
        )
        for key, state in self.sections.items():
            if isinstance(self.section_preferences.get(key), dict):
                state.load_ui_values(self.section_preferences[key])
        for name in ("position", "anchor", "vertical_scroll", "horizontal_scroll"):
            value = values.get(name)
            if type(value) is int and 0 <= value <= 2_147_483_647:
                setattr(self, name, value)
        scale = values.get("text_scale")
        if type(scale) is int and 75 <= scale <= 200:
            self.text_scale = scale

    def restore(self, editor):
        if hasattr(editor, "select_section"):
            editor.select_section(self.active_section, capture=False)
        else:
            self.restore_position(editor)

    def restore_position(self, editor):
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
