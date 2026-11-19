import math
from html import escape

from PySide6.QtCore import QLineF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsItem, QMenu


class GridLayer(QGraphicsItem):
    def __init__(self, grid, view):
        super().__init__()
        self.grid, self.view = grid, view
        self.rect = QRectF(0, 0, view.map_width, view.map_height)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption)
        self.setZValue(0)
        self.last_line_count = 0

    def boundingRect(self):
        return self.rect

    def paint(self, painter, option, widget=None):
        grid = self.grid
        self.last_line_count = 0
        if not grid.enabled or grid.cell_size * abs(painter.worldTransform().m11()) < 5:
            return  # Dense grids disappear visually; snap/world coordinates remain exact.
        rect = option.exposedRect.intersected(self.boundingRect()).intersected(
            self.view.mapToScene(self.view.viewport().rect()).boundingRect())
        color = QColor("#ceb075")
        color.setAlphaF(grid.opacity)
        pen = QPen(color, 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        for axis, offset in [("x", grid.offset_x), ("y", grid.offset_y)]:
            start = rect.left() if axis == "x" else rect.top()
            stop = rect.right() if axis == "x" else rect.bottom()
            first = math.ceil((start - offset) / grid.cell_size)
            last = math.floor((stop - offset) / grid.cell_size)
            if last - first > 2048:
                continue
            for index in range(first, last + 1):
                point = offset + index * grid.cell_size
                if axis == "x":
                    painter.drawLine(QLineF(point, rect.top(), point, rect.bottom()))
                else:
                    painter.drawLine(QLineF(rect.left(), point, rect.right(), point))
                self.last_line_count += 1


class TokenItem(QGraphicsItem):
    def __init__(self, token, view, root, asset_path, provider, broken):
        super().__init__()
        self.token, self.view = token, view
        self.root, self.asset_path, self.provider = root, asset_path, provider
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, view._background is not None)
        self.setPos(token.x, token.y)
        self.setZValue(10 + token.z)
        self.base_tip = token.title + (" · Разорванная ссылка на Card" if broken else "")
        self.broken = broken
        self.setToolTip("<qt>" + escape(self.base_tip) + "</qt>")

    def set_value(self, token, root, asset_path, provider, broken):
        if ((token.width, token.height) != (self.token.width, self.token.height)):
            self.prepareGeometryChange()
        if (token.x, token.y) != (self.token.x, self.token.y):
            self.setPos(token.x, token.y)
        self.token = token
        self.root, self.asset_path, self.provider = root, asset_path, provider
        self.broken = broken
        self.base_tip = token.title + (" · Разорванная ссылка на Card" if broken else "")
        self.setToolTip("<qt>" + escape(self.base_tip) + "</qt>")
        self.setZValue(10 + token.z)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                     self.view._background is not None)
        self.update()

    def boundingRect(self):
        token = self.token
        return QRectF(-token.width / 2, -token.height / 2, token.width, token.height)

    def paint(self, painter, option, widget=None):
        rect = self.boundingRect()
        image = self.provider(self.root, self.asset_path) if self.asset_path else None
        if image is not None and not image.isNull():
            painter.drawImage(rect, image)
            self.setToolTip("<qt>" + escape(self.base_tip) + "</qt>")
        else:
            message = self.base_tip + (" · Изображение загружается" if self.asset_path
                and image is None else " · Изображение отсутствует или повреждено")
            self.setToolTip("<qt>" + escape(message) + "</qt>")
            painter.fillRect(rect, QColor("#713d49"))
            painter.setPen(QColor("#f5d7dc"))
            painter.drawLine(rect.topLeft(), rect.bottomRight())
            painter.drawLine(rect.bottomLeft(), rect.topRight())
        pen = QPen(QColor("#ffe0a0" if self.isSelected() else "#59708e"),
                   3 if self.isSelected() else 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

    def mousePressEvent(self, event):
        self._drag_origin = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if getattr(self, "_drag_origin", self.pos()) == self.pos():
            return
        view, key, x, y = self.view, self.token.id, self.pos().x(), self.pos().y()
        QTimer.singleShot(0, view, lambda: view.token_moved.emit(key, x, y))

    def mouseDoubleClickEvent(self, event):
        self.view.token_action.emit(self.token.id, "open")
        event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu()
        for label, name in [("Открыть карточку", "open"),
                            ("Свойства: название, размер, связь…", "properties"),
                            ("Заменить изображение…", "image"),
                            ("Создать связанную карточку…", "create"),
                            ("Убрать связь", "unlink"), ("Удалить токен", "delete")]:
            action = menu.addAction(label)
            action.setData(name)
        chosen = menu.exec(event.screenPos())
        if chosen:
            self.view.token_action.emit(self.token.id, chosen.data())
        event.accept()
