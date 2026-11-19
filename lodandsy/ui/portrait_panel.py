from dataclasses import replace

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QDialog, QHBoxLayout, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from lodandsy.ui.icons import icon
from lodandsy.ui.portrait_crop_dialog import PortraitCropDialog


class PortraitImage(QToolButton):
    """Paint using the final content rectangle, independent of previous layout/pixmap sizes."""

    def __init__(self, parent):
        super().__init__(parent)
        self.source = None
        self.crop = (0, 0, 1, 1)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.source is None or self.source.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        frame = QRectF(self.contentsRect()).adjusted(2, 2, -2, -2)
        x, y, w, h = self.crop
        source = QRectF(
            x * self.source.width(),
            y * self.source.height(),
            w * self.source.width(),
            h * self.source.height(),
        )
        size = source.size().scaled(frame.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRectF(
            frame.center().x() - size.width() / 2,
            frame.center().y() - size.height() / 2,
            size.width(),
            size.height(),
        )
        painter.fillRect(frame, QColor("#191919"))
        painter.drawImage(target, self.source, source)


class PortraitPanel(QWidget):
    changed = Signal(object)
    image_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cardPortrait")
        self.setFixedSize(184, 184)
        self.portrait = None
        self._image = None
        self.image_provider = lambda key: None
        self.image = PortraitImage(self)
        self.image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image.setObjectName("portraitImage")
        self.image.setAccessibleName("Портрет карточки — выбрать или заменить изображение")
        self.image.setToolTip("Выбрать или заменить портрет")
        self.image.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.image.clicked.connect(self.image_requested)
        self.image.installEventFilter(self)
        self.actions = QWidget(self)
        actions = QHBoxLayout(self.actions)
        actions.setContentsMargins(4, 4, 4, 4)
        actions.setSpacing(2)
        self.replace = QToolButton()
        self.replace.setIcon(icon("rename"))
        self.replace.setToolTip("Заменить портрет")
        self.replace.clicked.connect(self.image_requested)
        self.crop_button = QToolButton()
        self.crop_button.setIcon(icon("crop"))
        self.crop_button.setToolTip("Кадрировать портрет")
        self.crop_button.clicked.connect(self.edit_crop)
        self.remove = QToolButton()
        self.remove.setIcon(icon("delete"))
        self.remove.setToolTip("Убрать портрет")
        self.remove.clicked.connect(lambda: self.changed.emit(None))
        for button in (self.replace, self.crop_button, self.remove):
            button.setAccessibleName(button.toolTip())
            button.installEventFilter(self)
            actions.addWidget(button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.image)
        self.actions.hide()
        self.set_portrait(None)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Enter, QEvent.Type.FocusIn):
            self.actions.setVisible(bool(self.portrait and self.portrait.asset_id))
        elif event.type() in (QEvent.Type.Leave, QEvent.Type.FocusOut):
            if not self.underMouse() and not any(
                b.hasFocus() for b in (self.image, self.replace, self.crop_button, self.remove)
            ):
                self.actions.hide()
        return super().eventFilter(obj, event)

    def leaveEvent(self, event):
        if not any(b.hasFocus() for b in (self.image, self.replace, self.crop_button, self.remove)):
            self.actions.hide()
        super().leaveEvent(event)

    def set_portrait(self, portrait):
        self.portrait = portrait
        if not portrait or not portrait.asset_id:
            self.actions.hide()
        self.refresh_image()

    def refresh_image(self, *_):
        self._image = (
            self.image_provider(self.portrait.asset_id)
            if self.portrait and self.portrait.asset_id
            else None
        )
        self._paint_image()

    def _paint_image(self):
        image = self._image
        available = image is not None and not image.isNull()
        self.image.source = image
        self.image.crop = self.portrait.crop if self.portrait else (0, 0, 1, 1)
        self.crop_button.setEnabled(available)
        if not available:
            self.image.setText(
                "＋\nПортрет"
                if not self.portrait or not self.portrait.asset_id
                else "Загрузка…"
                if image is None
                else "Портрет недоступен"
            )
            self.image.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        else:
            self.image.setText("")
        self.image.update()

    def edit_crop(self):
        if self._image is None or self._image.isNull() or not self.portrait:
            return
        dialog = PortraitCropDialog(self._image, self.portrait.crop, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.changed.emit(replace(self.portrait, crop=dialog.crop()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.actions.adjustSize()
        self.actions.move(max(0, self.width() - self.actions.width() - 4), 4)
        self.actions.raise_()

    def sizeHint(self):
        return QSize(184, 184)
