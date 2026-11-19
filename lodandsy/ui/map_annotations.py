import math
from html import escape

from PySide6.QtCore import QLineF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
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
        if not grid.enabled:
            return
        zoom = max(1e-9, abs(painter.worldTransform().m11()))
        self.detail_factor = 2 ** max(0, math.ceil(math.log2(8 / (grid.cell_size * zoom))))
        step = grid.cell_size * self.detail_factor
        rect = option.exposedRect.intersected(self.boundingRect()).intersected(
            self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        )
        color = QColor(grid.color)
        color.setAlphaF(grid.opacity)
        pen = QPen(color, 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        lines = []
        for axis, offset in [("x", grid.offset_x), ("y", grid.offset_y)]:
            start = rect.left() if axis == "x" else rect.top()
            stop = rect.right() if axis == "x" else rect.bottom()
            first = math.ceil((start - offset) / step)
            last = math.floor((stop - offset) / step)
            if last - first > 2048:
                continue
            for index in range(first, last + 1):
                point = offset + index * step
                if axis == "x":
                    lines.append(QLineF(point, rect.top(), point, rect.bottom()))
                else:
                    lines.append(QLineF(rect.left(), point, rect.right(), point))
                self.last_line_count += 1
        shadow = QColor("#000000")
        shadow.setAlphaF(grid.opacity)
        pen = QPen(shadow, 3)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLines(lines)
        pen = QPen(color, 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLines(lines)


class TokenItem(QGraphicsItem):
    def __init__(self, token, view, root, asset_path, provider, broken):
        super().__init__()
        self.token, self.view = token, view
        self.cell_size = view.grid.cell_size
        self.root, self.asset_path, self.provider = root, asset_path, provider
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, view._background is not None)
        self.setPos(token.x, token.y)
        self.setZValue(10 + token.z)
        self.base_tip = token.title + (" · Разорванная ссылка на документ" if broken else "")
        self.broken = broken
        self.setToolTip("<qt>" + escape(self.base_tip) + "</qt>")

    def set_value(self, token, root, asset_path, provider, broken):
        if (token.cells_w, token.cells_h, self.view.grid.cell_size) != (
            self.token.cells_w,
            self.token.cells_h,
            self.cell_size,
        ):
            self.prepareGeometryChange()
        self.cell_size = self.view.grid.cell_size
        if (token.x, token.y) != (self.token.x, self.token.y):
            self.setPos(token.x, token.y)
        self.token = token
        self.root, self.asset_path, self.provider = root, asset_path, provider
        self.broken = broken
        self.base_tip = token.title + (" · Разорванная ссылка на документ" if broken else "")
        self.setToolTip("<qt>" + escape(self.base_tip) + "</qt>")
        self.setZValue(10 + token.z)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable, self.view._background is not None
        )
        self.update()

    def boundingRect(self):
        token = self.token
        width, height = token.cells_w * self.cell_size, token.cells_h * self.cell_size
        return QRectF(-width / 2, -height / 2, width, height)

    def shape(self):
        path = QPainterPath()
        if self.token.kind == "character":
            path.addEllipse(self._circle())
        else:
            path.addRect(self.boundingRect())
        return path

    def _circle(self):
        rect = self.boundingRect()
        size = min(rect.width(), rect.height())
        return QRectF(-size / 2, -size / 2, size, size)

    def paint(self, painter, option, widget=None):
        rect = self.boundingRect()
        character = self.token.kind == "character"
        if character:
            rect = self._circle()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if character:
            painter.setClipPath(self.shape())
        image = self.provider(self.root, self.asset_path) if self.asset_path else None
        if image is not None and not image.isNull():
            if character:
                size = min(image.width(), image.height())
                source = QRectF((image.width() - size) / 2, (image.height() - size) / 2, size, size)
                painter.drawImage(rect, image, source)
            else:
                scale = min(rect.width() / image.width(), rect.height() / image.height())
                width, height = image.width() * scale, image.height() * scale
                painter.drawImage(QRectF(-width / 2, -height / 2, width, height), image)
            self.setToolTip("<qt>" + escape(self.base_tip) + "</qt>")
        else:
            message = self.base_tip + (
                " · Изображение загружается"
                if self.asset_path and image is None
                else " · Изображение отсутствует или повреждено"
            )
            self.setToolTip("<qt>" + escape(message) + "</qt>")
            painter.fillRect(rect, QColor("#713d49"))
            painter.setPen(QColor("#f5d7dc"))
            painter.drawLine(rect.topLeft(), rect.bottomRight())
            painter.drawLine(rect.bottomLeft(), rect.topRight())
        painter.restore()
        if not character and not self.isSelected():
            return
        pen = QPen(
            QColor("#ffe0a0" if self.isSelected() else "#ffffff"), 3 if self.isSelected() else 2
        )
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if character:
            painter.drawEllipse(rect)
        else:
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
        for label, name in [
            ("Открыть документ", "open"),
            ("Связать с документом…", "link"),
            ("Свойства: название, размер, связь…", "properties"),
            ("Заменить изображение…", "image"),
            ("Создать связанную карточку…", "create"),
            ("Убрать связь", "unlink"),
            ("Удалить токен", "delete"),
        ]:
            action = menu.addAction(label)
            action.setData(name)
        chosen = menu.exec(event.screenPos())
        if chosen:
            self.view.token_action.emit(self.token.id, chosen.data())
        event.accept()
