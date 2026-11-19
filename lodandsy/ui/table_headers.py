from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QToolButton

from lodandsy.ui.icons import icon


class AppendHeader(QHeaderView):
    append_requested = Signal()

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self.setSectionsMovable(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.plus = QToolButton(self.viewport())
        self.plus.setIcon(icon("plus"))
        self.plus.setAccessibleName(
            "Добавить столбец" if orientation == Qt.Orientation.Horizontal else "Добавить строку"
        )
        self.plus.setToolTip(self.plus.accessibleName())
        self.plus.clicked.connect(self.append_requested)
        self.sectionResized.connect(self.position_plus)
        self.sectionCountChanged.connect(self.position_plus)
        self.geometriesChanged.connect(self.position_plus)
        if orientation == Qt.Orientation.Horizontal:
            self.setMinimumHeight(32)
        else:
            self.setMinimumWidth(38)

    def position_plus(self, *args):
        horizontal = self.orientation() == Qt.Orientation.Horizontal
        index = self.logicalIndex(self.count() - 1) if self.count() else -1
        end = self.sectionViewportPosition(index) + self.sectionSize(index) if index >= 0 else 0
        if horizontal:
            self.plus.setGeometry(end, 0, 28, max(24, self.height()))
        else:
            self.plus.setGeometry(0, end, max(28, self.width()), 28)
        self.plus.show()
        self.plus.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_plus()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self.position_plus()


class TableView(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHorizontalHeader(AppendHeader(Qt.Orientation.Horizontal, self))
        self.setVerticalHeader(AppendHeader(Qt.Orientation.Vertical, self))
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.horizontalScrollBar().valueChanged.connect(self.horizontalHeader().position_plus)
        self.verticalScrollBar().valueChanged.connect(self.verticalHeader().position_plus)

    def updateGeometries(self):
        super().updateGeometries()
        if not isinstance(self.horizontalHeader(), AppendHeader) or not isinstance(
            self.verticalHeader(), AppendHeader
        ):
            return
        # Reserve scrollable footer space; the [+] controls are never model cells.
        self.horizontalScrollBar().setRange(
            0, max(0, self.horizontalHeader().length() + 28 - self.viewport().width())
        )
        self.verticalScrollBar().setRange(
            0, max(0, self.verticalHeader().length() + 28 - self.viewport().height())
        )
        self.horizontalHeader().position_plus()
        self.verticalHeader().position_plus()
