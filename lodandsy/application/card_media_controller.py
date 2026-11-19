"""Card-specific image commands over the shared media/resource contract."""

from pathlib import Path
from weakref import ref

from PySide6.QtGui import QTextCursor, QTextFormat, QTextImageFormat
from PySide6.QtWidgets import QFileDialog, QInputDialog
from shiboken6 import isValid


class CardMediaController:
    def __init__(self, window, cards, media, resources, ensure_project):
        self.window, self.cards, self.media, self.resources, self.ensure_project = (
            window,
            cards,
            media,
            resources,
            ensure_project,
        )

    @property
    def importing(self):
        return self.media.importing

    def request(self, editor, source=None):
        if self.importing or editor.text_edit.isReadOnly():
            return
        project = self.resources
        if project is None:
            return
        if project.store is None and not self.ensure_project():
            return
        if source is None:
            name, _ = QFileDialog.getOpenFileName(
                editor,
                "Вставить изображение",
                "",
                "Изображения (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
            )
            if not name:
                return
            source = Path(name)
        alt, accepted = QInputDialog.getText(
            editor, "Изображение", "Описание (alt):", text="Изображение"
        )
        if accepted:
            self.insert(editor, source, alt)

    def insert(self, editor, source, alt):
        project = self.resources
        if self.importing or project.store is None or editor.card_id is None:
            raise ValueError("Дождитесь импорта и выберите проект и карточку")
        card_id = editor.card_id
        section_key = editor.current_section
        cursor = QTextCursor(editor.text_edit.textCursor())
        document_ref = ref(cursor.document())
        # Insertion survives intervening edits without replacing unrelated text.
        cursor.setPosition(cursor.selectionEnd())
        cursor.setKeepPositionOnInsert(True)

        def publish(asset, error):
            if error:
                self.window.show_notice(error)
                return False
            if not any(item.id == card_id for item in self.cards.cards.all()):
                return False
            try:
                section = self.cards.cards.get(card_id).section(section_key)
            except ValueError:
                return False
            document = document_ref()
            if section.kind != "rich_text" or document is None or not isValid(document):
                return False
            cursor.beginEditBlock()
            image = QTextImageFormat()
            image.setName(asset.path)
            image.setWidth(400)
            image.setProperty(QTextFormat.Property.ImageAltText, alt)
            cursor.insertImage(image)
            cursor.endEditBlock()
            from lodandsy.application.rich_text_codec import serialize_document

            content = serialize_document(cursor.document())
            document.pending_content = content
            try:
                self.cards.update_section(card_id, section_key, content=content)
            except ValueError as error:
                self.cards.set_field_draft(card_id, section_key, content)
                self.window.show_notice(str(error))
            return True

        self.media.import_image(source, publish)

    def portrait(self, editor, source=None):
        from dataclasses import replace

        from lodandsy.domain.card import Portrait

        project = self.resources
        if self.importing or editor.card_id is None:
            return
        if project.store is None and not self.ensure_project():
            return
        key = editor.card_id
        if source is None:
            name, _ = QFileDialog.getOpenFileName(
                editor, "Портрет", "", "Изображения (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"
            )
            if not name:
                return
            source = Path(name)

        def publish(asset, error):
            if error:
                self.window.show_notice(error)
                return False
            if not any(card.id == key for card in self.cards.cards.all()):
                return False
            previous = self.cards.cards.get(key).portrait or Portrait()
            self.cards.update_card(
                key, portrait=replace(previous, asset_id=asset.id, crop=(0.0, 0.0, 1.0, 1.0))
            )
            return True

        self.media.import_image(source, publish)
