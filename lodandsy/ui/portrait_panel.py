from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from lodandsy.domain.card import Portrait


class PortraitPanel(QWidget):
    changed = Signal(object)
    image_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.portrait = None
        self.image_provider = lambda key: None
        self._image = None
        self.image = QLabel()
        self.image.setTextFormat(Qt.TextFormat.PlainText)
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setFixedHeight(150)
        self.caption = QLineEdit()
        self.caption.setMaxLength(2000)
        self.caption.setPlaceholderText("Подпись портрета (необязательно)")
        self.caption.editingFinished.connect(self._caption_changed)
        self.caption.textEdited.connect(self._caption_changed)
        self.alt = QLineEdit()
        self.alt.setMaxLength(2000)
        self.alt.setPlaceholderText("Описание изображения")
        self.alt.editingFinished.connect(self._caption_changed)
        self.alt.textEdited.connect(self._caption_changed)
        self.choose = QPushButton("Выбрать портрет…")
        self.choose.clicked.connect(self.image_requested)
        self.remove = QPushButton("Убрать портрет")
        self.remove.clicked.connect(lambda: self.changed.emit(None))
        self.add = QPushButton("Добавить портретный блок")
        self.add.clicked.connect(lambda: self.changed.emit(Portrait()))
        row = QHBoxLayout()
        row.addWidget(self.choose)
        row.addWidget(self.remove)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.addWidget(self.add)
        layout.addWidget(self.image)
        layout.addWidget(self.caption)
        layout.addWidget(self.alt)
        layout.addLayout(row)
        self.set_portrait(None)

    def set_portrait(self, portrait):
        self.portrait = portrait
        for widget in (self.image, self.caption, self.alt, self.choose, self.remove):
            widget.setVisible(portrait is not None)
        self.add.setVisible(portrait is None)
        if portrait is not None:
            self.caption.setText(portrait.caption)
            self.alt.setText(portrait.alt)
            self.choose.setText("Заменить портрет…" if portrait.asset_id else "Выбрать портрет…")
        self.refresh_image()

    def _caption_changed(self):
        if self.portrait is not None:
            updated = replace(self.portrait, caption=self.caption.text(), alt=self.alt.text())
            if updated != self.portrait:
                self.changed.emit(updated)

    def refresh_image(self, *_):
        self._image = (self.image_provider(self.portrait.asset_id)
                       if self.portrait and self.portrait.asset_id else None)
        self._paint_image()

    def _paint_image(self):
        image = self._image
        if image is None or image.isNull():
            self.image.setPixmap(QPixmap())
            self.image.setText("Портрет не выбран" if not self.portrait or
                               not self.portrait.asset_id else "Загрузка / изображение недоступно")
        else:
            self.image.setPixmap(QPixmap.fromImage(image).scaled(
                max(1, self.width()-12), 150, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        self.image.setAccessibleName(self.portrait.alt if self.portrait else "Портрет")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._paint_image()
