"""Session-only original-image overlay. Source decoding uses the shared bounded provider."""

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QToolButton, QWidget


class MapPortrait(QWidget):
    dismissed = Signal()

    def __init__(self, view, root, path, provider):
        super().__init__(view.viewport())
        self.view, self.root, self.path, self.provider = view, root, path, provider
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.close_button = QToolButton(self)
        self.close_button.setText("Закрыть ×")
        self.close_button.setToolTip("Закрыть изображение у всех · Escape")
        self.close_button.clicked.connect(self.dismissed)
        self.setGeometry(view.viewport().rect())
        view.viewport().installEventFilter(self)
        view.installEventFilter(self)
        self.show()
        self.raise_()

    def image_ready(self, root, name):
        if root == self.root and name == self.path:
            self.update()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            self.setGeometry(self.parentWidget().rect())
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.dismissed.emit()
            return True
        return False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.dismissed.emit()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        self.close_button.adjustSize()
        self.close_button.move(max(0, self.width() - self.close_button.width() - 12), 12)
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101010"))
        image = self.provider(self.root, self.path)
        if image is None or image.isNull():
            painter.setPen(QColor("#eeeeee"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Загрузка изображения…" if image is None else "Изображение недоступно",
            )
            return
        available = self.rect().adjusted(20, 48, -20, -20)
        if available.width() <= 0 or available.height() <= 0:
            return
        scale = min(available.width() / image.width(), available.height() / image.height())
        target = QRectF(0, 0, image.width() * scale, image.height() * scale)
        target.moveCenter(available.center())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(target, image, QRectF(image.rect()))
