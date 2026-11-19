from PySide6.QtCore import QSignalBlocker, QSizeF, Qt
from PySide6.QtGui import QColor, QImage, QPyTextObject, QTextFormat

from lodandsy.application.resource_paths import resolve_asset_image
from lodandsy.application.rich_html import validate_html
from lodandsy.application.rich_text_codec import OfflineDocument


class AssetImageObject(QPyTextObject):
    def __init__(self, document):
        super().__init__(document)
        self.document = document

    def intrinsicSize(self, document, position, format):
        image_format = format.toImageFormat()
        image = self.document.image(image_format.name())
        if image is None or image.isNull():
            return QSizeF(min(240, max(40, document.textWidth() - 24)), 48)
        requested = image_format.width() or min(600, image.width())
        width = min(requested, max(40, document.textWidth() - 24))
        return QSizeF(width, width * image.height() / image.width())

    def drawObject(self, painter, rect, document, position, format):
        image = self.document.image(format.toImageFormat().name())
        if image is None or image.isNull():
            painter.fillRect(rect, QColor("#253146"))
            painter.setPen(QColor("#aab7ca"))
            painter.drawText(
                rect,
                Qt.AlignmentFlag.AlignCenter,
                "Загрузка…" if image is None else "Изображение недоступно",
            )
        else:
            painter.drawImage(rect, image)


class RichDocument(OfflineDocument):
    """Session document; layout/images/zoom never rewrite canonical content."""

    def __init__(self, content, parent=None):
        super().__init__(parent)
        self.project_root, self.image_provider = None, None
        self.images, self.image_budget = {}, 0
        self._metrics = None
        self._image_handler = AssetImageObject(self)
        self.documentLayout().registerHandler(
            QTextFormat.ObjectTypes.ImageObject, self._image_handler
        )
        validate_html(content)
        self.setHtml(content)
        self.canonical_content = content

    def configure_resources(self, root, provider):
        if self.project_root != root:
            self.images.clear()
            self.image_budget = 0
        self.project_root, self.image_provider = root, provider

    def image(self, name):
        if name in self.images:
            return self.images[name]
        if resolve_asset_image(self.project_root, name) is None or self.image_provider is None:
            return QImage()
        if self.image_budget + 4 * 1024**2 > 8 * 1024**2:
            return QImage()
        image = self.image_provider(self.project_root, name)
        self.images[name] = image
        self.image_budget += 4 * 1024**2 if image is None else image.sizeInBytes()
        return image

    def image_ready(self, root, name):
        if root != self.project_root or name not in self.images or self.images[name] is not None:
            return
        self.image_budget -= 4 * 1024**2
        self.images.pop(name)
        self.image(name)
        blocker = QSignalBlocker(self)
        self.markContentsDirty(0, self.characterCount())
        del blocker

    def set_view_scale(self, scale, dpi):
        # Layout on a device with adjusted DPI scales all point sizes without editing formats.
        metrics = QImage(1, 1, QImage.Format.Format_ARGB32)
        metrics.setDotsPerMeterX(round(dpi * scale / 100 / 0.0254))
        metrics.setDotsPerMeterY(round(dpi * scale / 100 / 0.0254))
        blocker = QSignalBlocker(self)
        self.documentLayout().setPaintDevice(metrics)
        self._metrics = metrics  # Qt borrows this pointer; retain it for the document's lifetime.
        self.markContentsDirty(0, self.characterCount())
        del blocker
