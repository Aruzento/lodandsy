from PySide6.QtCore import QEvent, QModelIndex, QObject, QPersistentModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QStyledItemDelegate, QToolButton
from shiboken6 import isValid

from lodandsy.ui.icons import icon
from lodandsy.ui.theme import ICON_SIZE, SPACE_XS, TREE_ACTION_SIZE


class NavigatorDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(30, size.height()))
        return size


class NavigatorActions(QObject):
    """One menu button follows the pointer and stays anchored while its menu is open."""

    def __init__(self, panel):
        super().__init__(panel)
        self.panel, self.view = panel, panel.tree_view
        self.viewport = self.view.viewport()
        self._hovered = QPersistentModelIndex()
        self._menu_index = None
        button = self.menu_button = QToolButton(self.viewport)
        button.setObjectName("treeRowMenu")
        button.setIcon(icon("more_vertical"))
        button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        button.setAccessibleName("Действия документа")
        button.setToolTip("Действия документа (Shift+F10)")
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setFixedSize(TREE_ACTION_SIZE, TREE_ACTION_SIZE)
        button.hide()
        button.clicked.connect(self._open_from_button)
        self.view.setMouseTracking(True)
        self.viewport.setMouseTracking(True)
        self.viewport.installEventFilter(self)
        self.view.verticalScrollBar().valueChanged.connect(self._update_hover)
        self.view.horizontalScrollBar().valueChanged.connect(self._update_hover)
        self.view.expanded.connect(self._update_hover)
        self.view.collapsed.connect(self._update_hover)
        self.view.model().modelReset.connect(self._update_hover)
        self.view.model().rowsRemoved.connect(self._update_hover)
        self.view.model().rowsInserted.connect(self._update_hover)
        self.view.setItemDelegate(NavigatorDelegate(self.view))

    @property
    def index(self):
        return self._hovered if self._menu_index is None else self._menu_index

    def _set_hover(self, index):
        self._hovered = QPersistentModelIndex(index)
        self._position_button()

    def _update_hover(self, *_args):
        if self._menu_index is not None:
            self._position_button()
            return
        point = self.viewport.mapFromGlobal(QCursor.pos())
        index = self.view.indexAt(point) if self.viewport.rect().contains(point) else QModelIndex()
        self._set_hover(index)

    def _position_button(self):
        row = self.view.visualRect(self.index)
        area = QRect(
            self.viewport.width() - SPACE_XS - TREE_ACTION_SIZE,
            row.top() + (row.height() - TREE_ACTION_SIZE) // 2,
            TREE_ACTION_SIZE,
            TREE_ACTION_SIZE,
        )
        visible = row.isValid() and self.viewport.rect().contains(area)
        if visible:
            self.menu_button.move(area.topLeft())
        self.menu_button.setVisible(visible)

    def eventFilter(self, watched, event):
        if not isValid(self.view) or watched is not self.viewport:
            return False
        if event.type() == QEvent.Type.MouseMove and self._menu_index is None:
            self._set_hover(self.view.indexAt(event.position().toPoint()))
        elif event.type() == QEvent.Type.Leave and self._menu_index is None:
            if not self.viewport.rect().contains(self.viewport.mapFromGlobal(QCursor.pos())):
                self._set_hover(QModelIndex())
        elif event.type() == QEvent.Type.Resize:
            self._position_button()
        return False

    def _open_from_button(self):
        if self.index.isValid():
            button = self.menu_button
            self.show_menu(QModelIndex(self.index), button.mapToGlobal(button.rect().bottomLeft()))

    def show_menu(self, index, position):
        if self._menu_index is not None:
            return
        if index.isValid():
            self.view.setCurrentIndex(index)
        self._menu_index = QPersistentModelIndex(index)
        self._position_button()
        menu = self.panel.context_menu(index)
        try:
            menu.exec(position)
        finally:
            menu.deleteLater()
            self._menu_index = None
            self._update_hover()
