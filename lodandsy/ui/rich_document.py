import time
from collections import OrderedDict

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
        size = self.document.image_size(image_format.name())
        if size is None:
            return QSizeF(min(240, max(40, document.textWidth() - 24)), 48)
        requested = image_format.width() or min(600, size.width())
        width = min(requested, max(40, document.textWidth() - 24))
        return QSizeF(width, width * size.height() / size.width())

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
        self.images, self.image_budget = OrderedDict(), 0
        self._image_times = {}
        self.size_provider = None
        self._metrics = None
        self._image_handler = AssetImageObject(self)
        self.documentLayout().registerHandler(
            QTextFormat.ObjectTypes.ImageObject, self._image_handler
        )
        validate_html(content)
        self.setHtml(content)
        self.canonical_content = content
        self.pending_content = None

    def configure_resources(self, root, provider, size_provider=None):
        if self.project_root != root:
            self.release_images()
        self.project_root, self.image_provider, self.size_provider = root, provider, size_provider

    def release_images(self):
        self.images.clear()
        self._image_times.clear()
        self.image_budget = 0

    def image_size(self, name):
        if self.size_provider:
            return self.size_provider(self.project_root, name)
        image = self.image(name)
        return image.size() if image is not None and not image.isNull() else None

    def _evict(self):
        self.image_budget = sum(i.sizeInBytes() for i in self.images.values() if i is not None)
        while self.image_budget > 8 * 1024**2 or len(self.images) > 16:
            name, image = self.images.popitem(last=False)
            self._image_times.pop(name, None)
            if image is not None:
                self.image_budget -= image.sizeInBytes()

    def image(self, name):
        # Called by drawObject for the visible working set, never to decode every layout image.
        now = time.monotonic()
        if name in self.images and now - self._image_times.get(name, 0) < 0.25:
            self.images.move_to_end(name)
            return self.images[name]
        if resolve_asset_image(self.project_root, name) is None or self.image_provider is None:
            image = QImage()
        else:
            image = self.image_provider(self.project_root, name)
        self.images[name] = image
        self._image_times[name] = now
        self.images.move_to_end(name)
        self._evict()
        return image

    def image_ready(self, root, name):
        if root != self.project_root or name not in self.images or self.images[name] is not None:
            return
        self._image_times.pop(name, None)
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
