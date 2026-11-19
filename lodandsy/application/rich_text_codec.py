from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QFont, QImage, QTextDocument

from lodandsy.application.rich_html import sanitize_html


class OfflineDocument(QTextDocument):
    """A Qt codec document with no filesystem or network fallback."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDefaultFont(QFont("Segoe UI", 11))
        self._blocked = QImage(1, 1, QImage.Format.Format_ARGB32)
        self._blocked.fill(Qt.GlobalColor.transparent)

    def loadResource(self, resource_type, name):
        return (
            self._blocked
            if resource_type == QTextDocument.ResourceType.ImageResource
            else QByteArray(b"blocked-resource")
        )


def serialize_document(document):
    return sanitize_html(document.toHtml())[0]
