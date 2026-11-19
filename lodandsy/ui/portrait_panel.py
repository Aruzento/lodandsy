from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.domain.card import Portrait


class PortraitPanel(QWidget):
    changed = Signal(object)
    image_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cardPortrait")
        self.setMaximumWidth(220)
        self.portrait = None
        self.image_provider = lambda key: None
        self._image = None
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setTextFormat(Qt.TextFormat.PlainText)
        self.image.setFixedHeight(196)
        self.image.setMinimumWidth(120)
        self.image.setObjectName("portraitImage")
        self.caption_label = QLabel()
        self.caption_label.setTextFormat(Qt.TextFormat.PlainText)
        self.caption_label.setWordWrap(True)
        self.caption_label.setObjectName("mutedCaption")
        self.settings = QDialog(self)
        self.settings.setWindowTitle("Подпись и описание портрета")
        self.caption = QLineEdit()
        self.alt = QLineEdit()
        form = QFormLayout(self.settings)
        for label, widget in [("Подпись", self.caption), ("Описание", self.alt)]:
            widget.setMaxLength(2000)
            widget.textEdited.connect(self._caption_changed)
            widget.editingFinished.connect(self._caption_changed)
            form.addRow(label, widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.settings.reject)
        form.addRow(buttons)
        self.choose = QPushButton("Добавить портрет")
        self.choose.clicked.connect(self.image_requested)
        more = QToolButton()
        more.setText("…")
        more.setToolTip("Настройки портрета")
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        self.describe = menu.addAction("Подпись и описание…", self.settings.exec)
        self.remove = QAction("Убрать портрет", menu)
        self.remove.triggered.connect(lambda: self.changed.emit(None))
        menu.addAction(self.remove)
        more.setMenu(menu)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.choose, 1)
        row.addWidget(more)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.image)
        layout.addWidget(self.caption_label)
        layout.addLayout(row)
        self.set_portrait(None)

    def set_portrait(self, portrait):
        self.portrait = portrait
        for widget, value in [
            (self.caption, portrait.caption if portrait else ""),
            (self.alt, portrait.alt if portrait else "Портрет"),
        ]:
            if widget.text() != value:
                widget.setText(value)
        self.caption_label.setText(portrait.caption if portrait else "")
        self.caption_label.setVisible(bool(portrait and portrait.caption))
        self.choose.setText("Заменить…" if portrait and portrait.asset_id else "Добавить портрет")
        self.remove.setEnabled(portrait is not None)
        self.refresh_image()

    def _caption_changed(self):
        previous = self.portrait or Portrait()
        updated = replace(previous, caption=self.caption.text(), alt=self.alt.text())
        if updated != self.portrait:
            self.changed.emit(updated)

    def refresh_image(self, *_):
        self._image = (
            self.image_provider(self.portrait.asset_id)
            if self.portrait and self.portrait.asset_id
            else None
        )
        self._paint_image()

    def _paint_image(self):
        image = self._image
        self.image.setPixmap(QPixmap())
        if image is None or image.isNull():
            self.image.setText(
                "Добавьте портрет"
                if not self.portrait or not self.portrait.asset_id
                else "Загрузка…"
                if image is None
                else "Портрет недоступен"
            )
        else:
            self.image.setPixmap(
                QPixmap.fromImage(image).scaled(
                    max(1, self.width()),
                    196,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self.image.setAccessibleName(self.portrait.alt if self.portrait else "Портрет")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._paint_image()
