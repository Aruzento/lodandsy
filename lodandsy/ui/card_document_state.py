from PySide6.QtGui import QTextCursor

from lodandsy.ui.rich_document import RichDocument


class CardDocumentState:
    """Session document and cursor/zoom state, independent of the editor window."""

    def __init__(self, content, parent, primary_id=None):
        self.parent = parent
        self.sections = {}
        self.section_preferences = {}
        self.primary_id = primary_id
        self.active_section = primary_id
        self.document = RichDocument(content, parent)
        self.position = self.anchor = self.vertical_scroll = self.horizontal_scroll = 0
        self.text_scale = 100
        self.images_connected = False

    def capture(self, editor):
        self.active_section = editor.current_section
        target = self.existing(self.active_section)
        if target and editor.body.currentIndex() == 0:
            target.capture_position(editor)

    def section(self, key, content=None):
        from lodandsy.domain.card import EMPTY_DOCUMENT

        if key == self.primary_id:
            return self
        if key not in self.sections:
            self.sections[key] = CardDocumentState(content or EMPTY_DOCUMENT, self.parent)
            self.sections[key].load_ui_values(self.section_preferences.get(key, {}))
        return self.sections[key]

    def existing(self, key):
        return self if key is not None and key == self.primary_id else self.sections.get(key)

    def documents(self):
        return tuple(
            d
            for d in (self.document, *(s.document for s in self.sections.values()))
            if d is not None
        )

    def prune(self, live_ids):
        """Forget only removed sections. Surviving documents retain their native Undo stack."""
        live_ids = set(live_ids)
        for key in self.sections.keys() - live_ids:
            self.sections.pop(key).delete()
        self.section_preferences = {
            key: value for key, value in self.section_preferences.items() if key in live_ids
        }
        if self.primary_id is not None and self.primary_id not in live_ids:
            self.document.deleteLater()
            self.document, self.primary_id = None, None
        if self.active_section not in live_ids:
            self.active_section = None

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
        values["sections"] = {
            **self.section_preferences,
            **{key: state.position_values() for key, state in self.sections.items()},
        }
        return values

    def position_values(self):
        return {
            name: getattr(self, name)
            for name in ("position", "anchor", "vertical_scroll", "horizontal_scroll", "text_scale")
        }

    def load_ui_values(self, values):
        from lodandsy.domain.card import validate_card_id

        key = values.get("active_section")
        try:
            validate_card_id(key)
            self.active_section = key
        except ValueError:
            pass
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
        key = self.active_section
        editor.select_section(key, capture=False)
        target = self.existing(editor.current_section)
        if target and editor.body.currentIndex() == 0:
            target.restore_position(editor)

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
        if self.document is None:
            return
        pending = self.document.pending_content
        if self.document.canonical_content == content and pending is None:
            return
        if pending == content:
            self.document.canonical_content = content
            self.document.pending_content = None
            return
        cursor = QTextCursor(self.document)
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.removeSelectedText()
        cursor.insertHtml(content)
        cursor.endEditBlock()
        self.document.canonical_content = content
        self.document.pending_content = None
