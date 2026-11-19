from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDockWidget, QWidget


class FixedPanelHost(QDockWidget):
    """Native QMainWindow separators resize sidebars independently of the ADS workspace."""

    def __init__(self, title, object_name, area, panel, parent=None):
        super().__init__(title, parent)
        self.setObjectName(object_name)
        self.setAllowedAreas(area)
        self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.setTitleBarWidget(QWidget(self))
        self.setMinimumWidth(180)
        self.panel = panel
        self.last_width = 240 if area == Qt.DockWidgetArea.LeftDockWidgetArea else 300
        self.setWidget(panel)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible() and self.width() >= self.minimumWidth():
            self.last_width = self.width()

    def showEvent(self, event):
        width = self.last_width
        super().showEvent(event)
        QTimer.singleShot(
            0,
            self,
            lambda: self.parentWidget().resizeDocks([self], [width], Qt.Orientation.Horizontal),
        )
