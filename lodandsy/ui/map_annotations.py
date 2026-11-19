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
        self.setZValue(9999)
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
        # Keep world coordinates throughout: the paint engine already applies viewport/DPR offsets.
        painter.save()
        painter.setClipRect(self.boundingRect(), Qt.ClipOperation.IntersectClip)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        pen = QPen(color)
        pen.setWidth(0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLines(lines)
        painter.restore()


class TokenItem(QGraphicsItem):
    def __init__(self, token, presentation, view, root, asset_path, provider):
        super().__init__()
        self.token, self.presentation, self.view = token, presentation, view
        self.cell_size = view.grid.cell_size
        self.root, self.asset_path, self.provider = root, asset_path, provider
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.set_value(token, presentation, root, asset_path, provider)

    def set_value(self, token, presentation, root, asset_path, provider):
        if (presentation.cells_w, presentation.cells_h, self.view.grid.cell_size) != (
            self.presentation.cells_w,
            self.presentation.cells_h,
            self.cell_size,
        ):
            self.prepareGeometryChange()
        self.cell_size = self.view.grid.cell_size
        self.token, self.presentation = token, presentation
        self.setPos(token.x, token.y)
        self.root, self.asset_path, self.provider = root, asset_path, provider
        self.broken = presentation.missing
        overrides = [
            name
            for name, value in [
                ("подпись", token.label_override),
                ("изображение", token.image_override),
                ("вид", token.kind_override),
                ("размер", token.cells_w or token.cells_h),
            ]
            if value is not None
        ]
        self.base_tip = (
            presentation.label
            + (" · Разорванная ссылка на Card" if self.broken else "")
            + (" · " + presentation.summary if presentation.summary else "")
            + (" · Свои: " + ", ".join(overrides) if overrides else "")
        )
        self.setToolTip("<qt>" + escape(self.base_tip) + "</qt>")
        self.setZValue(10000 + token.z)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
            self.view._background is not None and self.view.role == "viewer",
        )
        self.update()

    def boundingRect(self):
        width, height = (
            self.presentation.cells_w * self.cell_size,
            self.presentation.cells_h * self.cell_size,
        )
        return QRectF(-width / 2, -height / 2, width, height)

    def shape(self):
        path = QPainterPath()
        if self.presentation.kind == "character":
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
        character = self.presentation.kind == "character"
        if character:
            rect = self._circle()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if character:
            painter.setClipPath(self.shape())
        image = self.provider(self.root, self.asset_path) if self.asset_path else None
        if image is not None and not image.isNull():
            x, y, w, h = self.presentation.crop
            source = QRectF(
                x * image.width(), y * image.height(), w * image.width(), h * image.height()
            )
            scale = min(rect.width() / source.width(), rect.height() / source.height())
            width, height = source.width() * scale, source.height() * scale
            painter.drawImage(QRectF(-width / 2, -height / 2, width, height), image, source)
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
            QColor("#e5e5e3" if self.isSelected() else "#ffffff"), 3 if self.isSelected() else 2
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
        if self.view.role == "editor":
            event.ignore()
            return
        self.view.token_action.emit(self.token.id, "open")
        event.accept()

    def contextMenuEvent(self, event):
        if self.view.role == "editor":
            event.ignore()
            return
        menu = QMenu()
        for label, name in [
            ("Открыть карточку", "open"),
            ("Свойства размещения…", "properties"),
            ("Переименовать карточку…", "rename"),
            ("Портрет карточки…", "image"),
            ("Своё изображение размещения…", "override-image"),
            ("Сбросить переопределения", "reset"),
            ("Удалить размещение", "delete"),
        ]:
            action = menu.addAction(label)
            action.setData(name)
        chosen = menu.exec(event.screenPos())
        if chosen:
            self.view.token_action.emit(self.token.id, chosen.data())
        event.accept()


class RasterObjectItem(QGraphicsItem):
    def __init__(self, value, layer, view, path, root, provider):
        super().__init__()
        self.view = view
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.set_value(value, layer, path, root, provider)

    def set_value(self, value, layer, path, root, provider):
        self.prepareGeometryChange()
        self.value, self.layer, self.path, self.root, self.provider = (
            value,
            layer,
            path,
            root,
            provider,
        )
        self.setPos(value.x, value.y)
        self.setRotation(value.rotation)
        self.setZValue(layer.position * 10 + value.z / 10000)
        self.setVisible(layer.visible)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
            self.view.role == "editor"
            and self.view.tool != "pan"
            and self.view._background is not None,
        )
        self.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
            if self.view.role == "editor"
            else Qt.MouseButton.NoButton
        )
        self.update()

    def boundingRect(self):
        return QRectF(0, 0, self.value.width, self.value.height)

    def paint(self, painter, option, widget=None):
        image = self.provider(self.root, self.path) if self.path else None
        rect = self.boundingRect()
        if image is not None and not image.isNull():
            painter.drawImage(rect, image)
            self.setToolTip("Изображение · " + self.layer.title)
        else:
            painter.fillRect(rect, QColor("#713d49"))
            painter.setPen(QColor("#f5d7dc"))
            painter.drawLine(rect.topLeft(), rect.bottomRight())
            self.setToolTip(
                "Изображение загружается"
                if image is None and self.path
                else "Ресурс отсутствует или повреждён"
            )
        if self.isSelected():
            pen = QPen(QColor("#e5e5e3"), 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawRect(rect)

    def mousePressEvent(self, event):
        self._origin = self.pos()
        self._dragging = True
        self._cancelled = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not getattr(self, "_cancelled", False):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._dragging = False
        if getattr(self, "_cancelled", False):
            self.setPos(self._origin)
            return
        if self.pos() != getattr(self, "_origin", self.pos()):
            key, x, y = self.value.id, max(0, self.x()), max(0, self.y())
            QTimer.singleShot(0, self.view, lambda: self.view.object_moved.emit(key, x, y))

    def contextMenuEvent(self, event):
        if self.view.role == "viewer":
            event.ignore()
            return
        menu = QMenu()
        menu.addAction("Размер, поворот и порядок…")
        delete = menu.addAction("Удалить объект")
        chosen = menu.exec(event.screenPos())
        if chosen:
            self.view.object_action.emit(
                self.value.id, "delete" if chosen == delete else "properties"
            )
        event.accept()
