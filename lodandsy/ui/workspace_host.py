import PySide6QtAds as ads
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from lodandsy.ui.workspace_placement import WorkspacePlacement


class WorkspaceHost(ads.CDockManager):
    """Qt ADS owns the entire workspace layout and native floating containers."""

    def __init__(self, shell: QMainWindow):
        super().__init__(shell)

    def create_document(self, key: str, title: str, content: QWidget):
        dock = ads.CDockWidget(self, title)
        dock.setObjectName(key)
        dock.setWidget(content)
        return dock

    def add_document(self, dock, placement: WorkspacePlacement, anchor=None):
        if placement == WorkspacePlacement.FLOATING:
            self.addDockWidgetFloating(dock)
        else:
            areas = {
                WorkspacePlacement.LEFT: ads.LeftDockWidgetArea,
                WorkspacePlacement.RIGHT: ads.RightDockWidgetArea,
                WorkspacePlacement.TOP: ads.TopDockWidgetArea,
                WorkspacePlacement.BOTTOM: ads.BottomDockWidgetArea,
                WorkspacePlacement.CENTER: ads.CenterDockWidgetArea,
            }
            self.addDockWidget(areas[placement], dock,
                               anchor.dockAreaWidget() if anchor is not None else None)

    def focus_document(self, dock):
        dock.show()
        dock.toggleView(True)
        area = dock.dockAreaWidget()
        if area is not None:
            area.setCurrentDockWidget(dock)
        floating = dock.floatingDockContainer()
        if floating is not None:
            if floating.isMinimized():
                floating.showNormal()
            floating.raise_()
            floating.activateWindow()
        else:
            self.window().show()
            self.window().raise_()
            self.window().activateWindow()
        self.setDockWidgetFocused(dock)
        dock.widget().setFocus(Qt.FocusReason.OtherFocusReason)

    def ensure_visible(self):
        screens = QApplication.screens()
        for window in [self.window(), *self.floatingWidgets()]:
            maximized = window.isMaximized()
            rect = window.normalGeometry() if maximized else window.geometry()
            screen = next((s for s in screens if s.availableGeometry().contains(rect.center())),
                          QApplication.primaryScreen())
            area = screen.availableGeometry()
            width, height = min(rect.width(), area.width()), min(rect.height(), area.height())
            x = max(area.left(), min(rect.x(), area.right() - width + 1))
            y = max(area.top(), min(rect.y(), area.bottom() - height + 1))
            if maximized:
                window.showNormal()
            window.setGeometry(x, y, width, height)
            if maximized:
                window.showMaximized()
