from PySide6.QtCore import QEvent, QObject, QPersistentModelIndex, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QToolButton
from shiboken6 import isValid

from lodandsy.ui.icons import icon
from lodandsy.ui.project_tree_model import NODE_KIND_ROLE


class NavigatorDelegate(QStyledItemDelegate):
    def __init__(self, actions, parent):
        super().__init__(parent)
        self.actions = actions

    def paint(self, painter, option, index):
        option = QStyleOptionViewItem(option)
        if index == self.actions.index:
            option.rect.adjust(0, 0, -64, 0)
        super().paint(painter, option, index)

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(30, size.height()))
        return size


class NavigatorActions(QObject):
    """Two real, keyboard-focusable controls for one selected/hovered row."""

    def __init__(self, panel):
        super().__init__(panel)
        self.panel, self.view = panel, panel.tree_view
        self.viewport = self.view.viewport()
        self.index = QPersistentModelIndex()
        self.open_button = QToolButton(self.view.viewport())
        self.menu_button = QToolButton(self.view.viewport())
        for button, name, glyph in [(self.open_button, "Открыть объект", "open"),
                                    (self.menu_button, "Действия объекта", "more")]:
            button.setIcon(icon(glyph))
            button.setAccessibleName(name)
            button.setToolTip(name)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setFixedSize(28, 26)
            button.hide()
        self.open_button.clicked.connect(self._open)
        self.menu_button.clicked.connect(self._menu)
        self.view.setMouseTracking(True)
        self.view.viewport().setMouseTracking(True)
        self.view.viewport().installEventFilter(self)
        self.view.selectionModel().currentChanged.connect(self.select_current)
        self.view.verticalScrollBar().valueChanged.connect(self.reposition)
        self.view.horizontalScrollBar().valueChanged.connect(self.reposition)
        self.view.expanded.connect(self.reposition)
        self.view.collapsed.connect(self.reposition)
        self.view.model().rowsRemoved.connect(self.select_current)
        self.view.model().rowsInserted.connect(self.reposition)
        self.view.setItemDelegate(NavigatorDelegate(self, self.view))

    def select_current(self, *_args):
        self.set_index(self.view.currentIndex())

    def set_index(self, index):
        self.index = QPersistentModelIndex(index)
        self.reposition()
        self.view.viewport().update()

    def reposition(self, *_args):
        if not self.index.isValid():
            self.open_button.hide()
            self.menu_button.hide()
            return
        rect = self.view.visualRect(self.index)
        visible = self.view.viewport().rect().intersects(rect) and rect.height() > 0
        kind = self.index.data(NODE_KIND_ROLE)
        self.open_button.setVisible(visible and kind != "section")
        self.menu_button.setVisible(visible)
        right = self.view.viewport().width() - 4
        y = rect.top() + max(0, (rect.height() - 26) // 2)
        self.menu_button.move(right - 28, y)
        self.open_button.move(right - 60, y)

    def eventFilter(self, watched, event):
        if not isValid(self.view):
            return False
        if watched is self.viewport:
            if event.type() == QEvent.Type.MouseMove:
                if not (self.open_button.hasFocus() or self.menu_button.hasFocus()):
                    index = self.view.indexAt(event.position().toPoint())
                    self.set_index(index if index.isValid() else self.view.currentIndex())
            elif event.type() == QEvent.Type.Resize:
                self.reposition()
            elif event.type() == QEvent.Type.Leave:
                if not self.viewport.rect().contains(self.viewport.mapFromGlobal(QCursor.pos())):
                    self.select_current()
        return super().eventFilter(watched, event)

    def _open(self):
        if self.index.isValid():
            self.view.setCurrentIndex(self.index)
            self.panel.request_open(self.index)

    def _menu(self):
        if self.index.isValid():
            self.view.setCurrentIndex(self.index)
            menu = self.panel.context_menu(self.index)
            try:
                menu.exec(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))
            finally:
                menu.deleteLater()
