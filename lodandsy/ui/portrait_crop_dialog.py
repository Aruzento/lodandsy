"""Crop changes normalized presentation only; the shared asset bytes are immutable."""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class CropCanvas(QWidget):
    changed = Signal(object)

    def __init__(self, image, crop, parent=None):
        super().__init__(parent)
        self.image = image
        self.center = QPointF(
            (crop[0] + crop[2] / 2) * image.width(), (crop[1] + crop[3] / 2) * image.height()
        )
        self.zoom = max(1.0, min(8.0, max(1 / crop[2], 1 / crop[3])))
        self.setMinimumSize(360, 320)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Кадрирование: перетащите изображение, колесо — масштаб")
        self._drag = None

    def frame_rect(self):
        height = max(40, min(self.height() - 64, (self.width() - 64) / 0.75))
        width = height * 0.75
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def scale_value(self):
        frame = self.frame_rect()
        return (
            max(frame.width() / self.image.width(), frame.height() / self.image.height())
            * self.zoom
        )

    def clamp(self):
        frame = self.frame_rect()
        scale = self.scale_value()
        half_x, half_y = frame.width() / scale / 2, frame.height() / scale / 2
        self.center.setX(max(half_x, min(self.image.width() - half_x, self.center.x())))
        self.center.setY(max(half_y, min(self.image.height() - half_y, self.center.y())))

    def crop(self):
        self.clamp()
        frame = self.frame_rect()
        scale = self.scale_value()
        width, height = (
            frame.width() / scale / self.image.width(),
            frame.height() / scale / self.image.height(),
        )
        x = max(0, min(1 - width, self.center.x() / self.image.width() - width / 2))
        y = max(0, min(1 - height, self.center.y() / self.image.height() - height / 2))
        return x, y, width, height

    def set_zoom(self, value):
        self.zoom = max(1.0, min(8.0, value / 100))
        self.clamp()
        self.update()
        self.changed.emit(self.crop())

    def reset(self):
        self.center = QPointF(self.image.width() / 2, self.image.height() / 2)
        self.set_zoom(100)

    def paintEvent(self, event):
        self.clamp()
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0b111a"))
        frame = self.frame_rect()
        scale = self.scale_value()
        target = QRectF(
            frame.center().x() - self.center.x() * scale,
            frame.center().y() - self.center.y() * scale,
            self.image.width() * scale,
            self.image.height() * scale,
        )
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(target, self.image)
        shade = QPainterPath()
        shade.addRect(QRectF(self.rect()))
        shade.addRect(frame)
        p.fillPath(shade, QColor(0, 0, 0, 170))
        pen = QPen(QColor("#e8edf4"), 1)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.drawRect(frame)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            delta = event.position() - self._drag
            self.center -= delta / self.scale_value()
            self._drag = event.position()
            self.clamp()
            self.update()
            self.changed.emit(self.crop())

    def mouseReleaseEvent(self, event):
        self._drag = None
        self.unsetCursor()

    def wheelEvent(self, event):
        self.set_zoom(self.zoom * 100 * (1.1 if event.angleDelta().y() > 0 else 1 / 1.1))
        event.accept()

    def keyPressEvent(self, event):
        delta = {
            Qt.Key.Key_Left: QPointF(-8, 0),
            Qt.Key.Key_Right: QPointF(8, 0),
            Qt.Key.Key_Up: QPointF(0, -8),
            Qt.Key.Key_Down: QPointF(0, 8),
        }.get(event.key())
        if delta is not None:
            self.center += delta / self.scale_value()
            self.clamp()
            self.update()
            self.changed.emit(self.crop())
            event.accept()
        else:
            super().keyPressEvent(event)


class PortraitCropDialog(QDialog):
    def __init__(self, image, crop, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Кадрировать портрет")
        self.resize(720, 540)
        self.canvas = CropCanvas(image, crop, self)
        self.preview = QLabel()
        self.preview.setFixedSize(140, 187)
        self.preview.setAccessibleName("Предварительный просмотр портрета")
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(100, 800)
        self.zoom.setValue(round(self.canvas.zoom * 100))
        self.zoom.setAccessibleName("Масштаб изображения")
        self.zoom.valueChanged.connect(self.canvas.set_zoom)
        reset = QPushButton("Сбросить")
        reset.clicked.connect(lambda: (self.canvas.reset(), self.zoom.setValue(100)))
        side = QVBoxLayout()
        side.addWidget(QLabel("Предпросмотр"))
        side.addWidget(self.preview)
        side.addStretch()
        side.addWidget(QLabel("Масштаб"))
        side.addWidget(self.zoom)
        side.addWidget(reset)
        row = QHBoxLayout()
        row.addWidget(self.canvas, 1)
        row.addLayout(side)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Применить")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(row, 1)
        layout.addWidget(buttons)
        self.canvas.changed.connect(self._preview)
        self._preview(self.canvas.crop())

    def _preview(self, crop):
        image = self.canvas.image
        x, y, w, h = crop
        cut = image.copy(
            round(x * image.width()),
            round(y * image.height()),
            max(1, round(w * image.width())),
            max(1, round(h * image.height())),
        )
        self.preview.setPixmap(
            QPixmap.fromImage(cut).scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def crop(self):
        return self.canvas.crop()
