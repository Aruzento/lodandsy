from pathlib import Path

from PySide6.QtCore import QByteArray, QSignalBlocker, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QImage, QImageReader, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.application.markdown_links import preview_markdown, resolve_asset_image
from lodandsy.ui.icons import icon


class PreviewDocument(QTextDocument):
    def __init__(self, resource_provider, parent):
        super().__init__(parent)
        self._resource_provider = resource_provider
        self._blocked_image = QImage(1, 1, QImage.Format.Format_ARGB32)
        self._blocked_image.fill(Qt.GlobalColor.transparent)

    def loadResource(self, resource_type: int, name: QUrl):
        # Override at document level: Qt's default document loader can otherwise
        # read file:// after a browser resource provider returns an empty result.
        result = self._resource_provider(resource_type, name)
        if result is not None:
            return result
        # A valid sentinel prevents Qt's built-in local-file fallback.
        if resource_type == QTextDocument.ResourceType.ImageResource:
            return self._blocked_image
        return QByteArray(b"blocked-resource")


class MarkdownBrowser(QTextBrowser):
    project_root: Path | None = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._images: dict[str, QImage | None] = {}
        self._image_pixels = 0
        self.setDocument(PreviewDocument(self.loadResource, self))

    def _image(self, name: str) -> QImage | None:
        if name in self._images:
            return self._images[name]
        self._images[name] = None
        path = resolve_asset_image(self.project_root, name)
        if path is None:
            return None
        reader = QImageReader(str(path))
        if bytes(reader.format()).lower() not in {b"png", b"jpeg", b"bmp", b"gif", b"webp"}:
            return None
        size = reader.size()
        pixels = size.width() * size.height()
        if not size.isValid() or self._image_pixels + pixels > 64_000_000:
            return None
        image = reader.read()
        if image.isNull():
            return None
        self._image_pixels += pixels
        self._images[name] = image
        return image

    def loadResource(self, resource_type: int, name: QUrl):
        if resource_type == QTextDocument.ResourceType.ImageResource:
            return self._image(name.toString())
        return None

    def render_markdown(self, source: str):
        scroll = self.verticalScrollBar().value()
        self._images.clear()
        self._image_pixels = 0
        self.setDocument(PreviewDocument(self.loadResource, self))
        self.setMarkdown(preview_markdown(source))
        replacements = []
        block = self.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().isImageFormat():
                    name = fragment.charFormat().toImageFormat().name()
                    if self._image(name) is None:
                        message = (
                            "[Удалённое изображение заблокировано]"
                            if QUrl(name).scheme().lower() in {"http", "https"}
                            else "[Изображение недоступно: проверьте assets, формат и размер]"
                        )
                        replacements.append((fragment.position(), fragment.length(), message))
                iterator += 1
            block = block.next()
        for position, length, message in reversed(replacements):
            cursor = QTextCursor(self.document())
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(message)
        self.verticalScrollBar().setValue(scroll)


class CardEditorWidget(QWidget):
    content_changed = Signal(str, str)
    link_activated = Signal(QUrl)
    preview_rendered = Signal()
    copy_link_requested = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.setObjectName("cardEditor")

        self._card_id: str | None = None

        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setObjectName("cardContentEditor")
        self.text_edit.setPlaceholderText(
            "Write Markdown..."
        )
        self.text_edit.setEnabled(False)

        self.mode_combo = QComboBox(self)
        self.mode_combo.addItems(["Источник", "Просмотр", "Рядом"])
        self.mode_combo.setEnabled(False)
        self.copy_link_button = QToolButton(self)
        self.copy_link_button.setText("Копировать ссылку на карточку")
        self.copy_link_button.setIcon(icon("link"))
        self.copy_link_button.setToolTip("Копировать готовую Markdown-ссылку на эту карточку")
        self.copy_link_button.setEnabled(False)
        self.copy_link_button.clicked.connect(self._copy_link)
        self.preview = MarkdownBrowser(self)
        self.preview.setOpenLinks(False)
        self.preview.setOpenExternalLinks(False)
        self.preview.anchorClicked.connect(self.link_activated.emit)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.addWidget(self.text_edit)
        self.splitter.addWidget(self.preview)
        self.link_status = QLabel(self)
        self.link_status.setStyleSheet("color: #f19a9a; padding: 5px;")
        self.link_status.setTextFormat(Qt.TextFormat.PlainText)
        self.link_status.setWordWrap(True)
        self.link_status.hide()
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(150)
        self._preview_timer.timeout.connect(self.render_preview)
        self.mode_combo.currentIndexChanged.connect(self._set_view_mode)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.copy_link_button)
        layout.addWidget(self.splitter, 1)
        layout.addWidget(self.link_status)
        self._set_view_mode(0)

        self.text_edit.textChanged.connect(
            self._on_text_changed
        )

    @property
    def card_id(self) -> str | None:
        return self._card_id

    def _set_view_mode(self, mode):
        self.text_edit.setVisible(mode != 1)
        self.preview.setVisible(mode != 0)
        if mode:
            self.render_preview()

    def render_preview(self):
        if self.mode_combo.currentIndex() != 0:
            self.preview.render_markdown(self.text_edit.toPlainText())
            self.preview_rendered.emit()

    def _copy_link(self):
        if self._card_id is not None:
            self.copy_link_requested.emit(self._card_id)

    def show_link_error(self, message: str):
        self.link_status.setText(message)
        self.link_status.setVisible(bool(message))

    def set_document(self, card_id: str, document: QTextDocument) -> None:
        blocker = QSignalBlocker(self.text_edit)
        self._card_id = card_id
        self.text_edit.setDocument(document)
        self.text_edit.setEnabled(True)
        self.mode_combo.setEnabled(True)
        self.copy_link_button.setEnabled(True)
        self.render_preview()
        del blocker

    def set_card(
        self,
        card_id: str,
        content: str,
    ) -> None:
        if self._card_id == card_id and self.text_edit.toPlainText() == content:
            return
        blocker = QSignalBlocker(self.text_edit)
        if self._card_id == card_id:
            cursor = QTextCursor(self.text_edit.document())
            cursor.beginEditBlock()
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.insertText(content)
            cursor.endEditBlock()
        else:
            self.text_edit.setPlainText(content)
        self._card_id = card_id
        self.text_edit.setEnabled(True)
        self.mode_combo.setEnabled(True)
        self.copy_link_button.setEnabled(True)
        self.render_preview()

        del blocker

    def clear_card(self) -> None:
        self._card_id = None

        blocker = QSignalBlocker(self.text_edit)

        self.text_edit.clear()
        self.text_edit.setEnabled(False)
        self.mode_combo.setEnabled(False)
        self.copy_link_button.setEnabled(False)
        self.preview.clear()
        self.link_status.hide()

        del blocker

    def _on_text_changed(self) -> None:
        if self._card_id is None:
            return

        self.content_changed.emit(
            self._card_id,
            self.text_edit.toPlainText(),
        )
        if self.mode_combo.currentIndex() != 0:
            self._preview_timer.start()
