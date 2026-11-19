from html import escape
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QTextCursor, QTextFormat, QTextImageFormat
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.application.rich_html import allowed_link, sanitize_html
from lodandsy.application.rich_text_codec import serialize_document
from lodandsy.domain.card import EMPTY_DOCUMENT
from lodandsy.ui.portrait_panel import PortraitPanel
from lodandsy.ui.rich_document import RichDocument
from lodandsy.ui.rich_toolbar import RichToolbar


class RichTextEdit(QTextEdit):
    image_requested = Signal(object)
    link_activated = Signal(QUrl)
    notice = Signal(str)

    def canInsertFromMimeData(self, source):
        return source.hasImage() or source.hasUrls() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if self.isReadOnly():
            return
        if source.hasImage():
            self.image_requested.emit(source.imageData())
        elif source.hasUrls():
            urls = source.urls()
            if len(urls) == 1 and urls[0].isLocalFile():
                self.image_requested.emit(Path(urls[0].toLocalFile()))
        elif source.hasHtml():
            try:
                html, warnings = sanitize_html(source.html())
                self.textCursor().insertHtml(html)
                if warnings:
                    self.notice.emit("Некоторые объекты вставки заблокированы: " + warnings[0])
            except ValueError as error:
                self.notice.emit(str(error))
        elif source.hasText():
            if len(source.text().encode("utf-8")) > 2**20:
                self.notice.emit("Текст вставки превышает 1 MiB")
            else:
                self.textCursor().insertText(source.text())

    def mouseReleaseEvent(self, event):
        target = self.anchorAt(event.position().toPoint())
        if (
            event.button() == Qt.MouseButton.LeftButton
            and target
            and (self.isReadOnly() or event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        ):
            self.link_activated.emit(QUrl(target))
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class CardEditorWidget(QWidget):
    image_requested = Signal(object)
    content_changed = Signal(str, str)
    link_activated = Signal(QUrl)
    links_changed = Signal()
    copy_link_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._card_id, self._content = None, None
        self.entity_options = lambda: ()
        self.text_edit = RichTextEdit(self)
        self.text_edit.setObjectName("visualCardEditor")
        self.text_edit.setDocument(RichDocument(EMPTY_DOCUMENT, self.text_edit))
        self.text_edit.setPlaceholderText("Начните писать…")
        self.text_edit.image_requested.connect(self.image_requested)
        self.text_edit.link_activated.connect(self.link_activated)
        self.text_edit.notice.connect(self.show_link_error)
        self.text_edit.textChanged.connect(self._changed)
        self.copy_link_button = QToolButton()
        self.copy_link_button.setText("Копировать ссылку")
        self.copy_link_button.clicked.connect(lambda: self.copy_link_requested.emit(self.card_id))
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self.copy_link_button)
        self.format_toolbar = RichToolbar(self)
        self.link_status = QLabel()
        self.link_status.setTextFormat(Qt.TextFormat.PlainText)
        self.link_status.setWordWrap(True)
        self.link_status.setStyleSheet("color:#f19a9a")
        self.link_status.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        layout.addWidget(self.format_toolbar)
        self.portrait_panel = PortraitPanel(self)
        layout.addWidget(self.portrait_panel)
        layout.addWidget(self.text_edit, 1)
        layout.addWidget(self.link_status)

    @property
    def card_id(self):
        return self._card_id

    def set_document(self, card_id, document):
        blocker = QSignalBlocker(self.text_edit)
        self._card_id = card_id
        self.text_edit.setDocument(document)
        self._content = document.canonical_content
        del blocker
        self.format_toolbar.sync_paragraph()
        self.refresh_links()

    def set_card(self, card_id, content):
        if self.card_id == card_id and content == self._content:
            return
        # External updates preserve the session document and use one native Undo command.
        blocker = QSignalBlocker(self.text_edit)
        cursor = QTextCursor(self.text_edit.document())
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.removeSelectedText()
        cursor.insertHtml(content)
        cursor.endEditBlock()
        self._card_id, self._content = card_id, content
        self.text_edit.document().canonical_content = content
        del blocker

    def _changed(self):
        if self.card_id is None:
            return
        try:
            content = serialize_document(self.text_edit.document())
        except ValueError as error:
            blocker = QSignalBlocker(self.text_edit)
            self.text_edit.undo()
            del blocker
            self.show_link_error(str(error))
            return
        if content != self._content:
            self._content = content
            self.text_edit.document().canonical_content = content
            self.content_changed.emit(self.card_id, content)
            self.links_changed.emit()

    def clear_card(self):
        self._card_id = None
        blocker = QSignalBlocker(self.text_edit)
        self.text_edit.clear()
        del blocker
        self.text_edit.setEnabled(False)

    def refresh_links(self):
        self.links_changed.emit()

    def set_view_scale(self, scale):
        document = self.text_edit.document()
        if hasattr(document, "set_view_scale"):
            document.set_view_scale(scale, self.text_edit.logicalDpiY())
            self.text_edit.viewport().update()

    def show_link_error(self, message):
        self.link_status.setText(message)
        self.link_status.setVisible(bool(message))

    def open_current_link(self):
        href = self.text_edit.textCursor().charFormat().anchorHref()
        if href:
            self.link_activated.emit(QUrl(href))

    def request_link(self):
        options = tuple(self.entity_options())
        labels = [
            "Внешняя HTTP/HTTPS-ссылка…",
            *[f"{e.title} · {e.kind} · {e.id}" for e in options],
        ]
        choice, ok = QInputDialog.getItem(self, "Вставить ссылку", "Документ:", labels, 0, False)
        if not ok:
            return
        cursor = self.text_edit.textCursor()
        label = cursor.selectedText()
        if choice == labels[0]:
            href, ok = QInputDialog.getText(self, "Внешняя ссылка", "HTTP/HTTPS URL:")
            if not ok:
                return
            if not href.startswith(("https://", "http://")) or not allowed_link(href):
                self.show_link_error("Разрешены только корректные HTTP/HTTPS-ссылки")
                return
            label = label or href
        else:
            entity = options[labels.index(choice) - 1]
            href, label = f"lodandsy://entity/{entity.id}", label or entity.title
        cursor.insertHtml(f'<a href="{escape(href, quote=True)}">{escape(label)}</a>')

    def insert_asset(self, cursor, path, alt):
        format = QTextImageFormat()
        format.setName(path)
        format.setWidth(400)
        format.setProperty(QTextFormat.Property.ImageAltText, alt)
        cursor.insertImage(format)

    def contextMenuEvent(self, event):
        menu = self.text_edit.createStandardContextMenu()
        if self.text_edit.textCursor().charFormat().anchorHref():
            action = QAction("Открыть ссылку", menu)
            action.triggered.connect(self.open_current_link)
            menu.addAction(action)
        menu.exec(event.globalPos())
        menu.deleteLater()
