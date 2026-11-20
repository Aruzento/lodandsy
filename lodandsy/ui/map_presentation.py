"""Player-only surface; the Maps owner supplies the canonical model and GM camera."""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QVBoxLayout, QWidget

from lodandsy.ui.map_widget import MapView


class MapPresentation(QWidget):
    closed = Signal()

    def __init__(self, title, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("Презентация · " + title)
        self.resize(960, 640)
        self.view = MapView("player")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.view)
        self.view.fullscreen_requested.connect(self.toggle_fullscreen)
        self.view.exit_fullscreen_requested.connect(self.showNormal)
        QGuiApplication.instance().screenRemoved.connect(self._screen_removed)

    def image_ready(self, *_args):
        self.view.viewport().update()

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def _screen_removed(self, _screen):
        screens = QGuiApplication.screens()
        if screens and not any(
            s.availableGeometry().intersects(self.frameGeometry()) for s in screens
        ):
            self.showNormal()
            self.setGeometry(screens[0].availableGeometry().adjusted(40, 40, -40, -40))

    def follow_camera(self, rect):
        self.view.follow_camera(QRectF(rect))

    def closeEvent(self, event):
        self.view._display_ready = False
        self.closed.emit()
        super().closeEvent(event)
