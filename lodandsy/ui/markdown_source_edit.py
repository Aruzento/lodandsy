from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QPlainTextEdit


class MarkdownSourceEdit(QPlainTextEdit):
    zoom_requested = Signal(int)
    image_requested = Signal(object)

    def _image_source(self, mime):
        if mime.hasImage():
            image = QImage(mime.imageData())
            if not image.isNull():
                return image
        if mime.hasUrls() and len(mime.urls()) == 1:
            url = mime.urls()[0]
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
                    return path
        return None

    def canInsertFromMimeData(self, mime):
        return self._image_source(mime) is not None or super().canInsertFromMimeData(mime)

    def insertFromMimeData(self, mime):
        source = self._image_source(mime)
        if source is not None:
            self.image_requested.emit(source)
        else:
            super().insertFromMimeData(mime)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y():
                self.zoom_requested.emit(10 if event.angleDelta().y() > 0 else -10)
            event.accept()
            return
        super().wheelEvent(event)
