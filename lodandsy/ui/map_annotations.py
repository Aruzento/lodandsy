import math
from html import escape

from PySide6.QtCore import QEvent, QLineF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QMenu
from shiboken6 import isValid

from lodandsy.ui.icons import icon


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
        self.object_card = False
        self.has_inventory = False
        self.transform_preview = None
        self._muted_image = None
        self._muted_key = None
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, view.role != "player")
        self.set_value(token, presentation, root, asset_path, provider)

    def set_value(self, token, presentation, root, asset_path, provider):
        if (
            presentation.cells_w, presentation.cells_h, self.view.grid.cell_size
        ) != (
            self.presentation.cells_w,
            self.presentation.cells_h,
            self.cell_size,
        ) or (self.transform_preview is not None and self.token != token):
            self.prepareGeometryChange()
            self.transform_preview = None
        self.cell_size = self.view.grid.cell_size
        self.token, self.presentation = token, presentation
        position = self.transform_preview or token
        self.setPos(position.x, position.y)
        self.setRotation(position.rotation)
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
            self.view._background is not None and self.view.token_interaction_enabled,
        )
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
            self.view.role != "player",
        )
        self.update()

    @property
    def can_transform(self):
        return (
            self.object_card and self.view.token_interaction_enabled
            and self.view._background is not None and self.isVisible()
        )

    def set_transform_preview(self, token):
        if token == self.token:
            token = None
        if token == self.transform_preview:
            return
        self.prepareGeometryChange()
        self.transform_preview = token
        position = token or self.token
        self.setPos(position.x, position.y)
        self.setRotation(position.rotation)
        self.update()

    def boundingRect(self):
        preview = self.transform_preview
        width, height = self.presentation.cells_w, self.presentation.cells_h
        if preview is not None:
            width = width if preview.cells_w is None else preview.cells_w
            height = height if preview.cells_h is None else preview.cells_h
        width *= self.cell_size
        height *= self.cell_size
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
        if self.token.hidden and self.view.role == "player":
            return
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
            if self.token.hidden or self.token.dead:
                image = self._grayscale(image)
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
        self._paint_status(painter, rect)
        selected = self.isSelected()
        tools = getattr(self.view, "vector_tools", None)
        if not character and (not selected or (tools and tools.selected_transform_item() is self)):
            return
        pen = QPen(
            QColor("#e5e5e3" if selected else "#ffffff"), 3 if selected else 2
        )
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if character:
            painter.drawEllipse(rect)
        else:
            painter.drawRect(rect)

    def _grayscale(self, image):
        key = image.cacheKey()
        if key != self._muted_key:
            gray = image.convertToFormat(QImage.Format.Format_Grayscale8).convertToFormat(
                QImage.Format.Format_ARGB32_Premultiplied
            )
            if image.hasAlphaChannel():
                painter = QPainter(gray)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
                painter.drawImage(0, 0, image)
                painter.end()
            self._muted_image, self._muted_key = gray, key
        return self._muted_image

    def _paint_status(self, painter, rect):
        if not (self.token.hidden or self.token.dead):
            return
        transform = painter.worldTransform()
        painter.save()
        painter.resetTransform()
        if self.token.dead:
            center = transform.map(rect.center()).toPoint()
            icon("token_dead", 24, stroke_width=2, tint="#f47778").paint(
                painter, QRect(center.x() - 12, center.y() - 12, 24, 24)
            )
        if self.token.hidden:
            edge = transform.map(rect.topRight()).toPoint()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#202020"))
            painter.drawEllipse(edge, 10, 10)
            icon("eye_off").paint(painter, QRect(edge.x() - 8, edge.y() - 8, 16, 16))
        painter.restore()

    def mousePressEvent(self, event):
        self._drag_origin = self.pos()
        self._dragging = True
        self.view.measurement_changed.emit(
            (self.token.id, (self.x(), self.y()), (self.x(), self.y()))
        )
        self._cancelled = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._cancelled:
            return
        super().mouseMoveEvent(event)
        self.setPos(
            max(0, min(self.view.map_width, self.x())), max(0, min(self.view.map_height, self.y()))
        )
        self.view.measurement_changed.emit(
            (self.token.id, (self._drag_origin.x(), self._drag_origin.y()), (self.x(), self.y()))
        )
        self.view.transient_changed.emit("token", self.token.id, self.x(), self.y())

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._dragging = False
        self.view.measurement_changed.emit(None)
        if self._cancelled:
            self.setPos(self._drag_origin)
            return
        if getattr(self, "_drag_origin", self.pos()) == self.pos():
            return
        view, key, x, y = self.view, self.token.id, self.pos().x(), self.pos().y()
        QTimer.singleShot(0, view, lambda: view.token_moved.emit(key, x, y))

    def sceneEvent(self, event):
        if event.type() == QEvent.Type.UngrabMouse and getattr(self, "_dragging", False):
            self._dragging = False
            self._cancelled = True
            self.setPos(self._drag_origin)
            self.view.measurement_changed.emit(None)
            self.view.transient_changed.emit("token", self.token.id, self.x(), self.y())
        return super().sceneEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.view.role != "viewer":
            event.ignore()
            return
        self.view.token_action.emit(self.token.id, "open")
        event.accept()

    def contextMenuEvent(self, event):
        view = self.view
        if view.role != "viewer":
            event.ignore()
            return
        menu = QMenu()
        for label, name in [
            ("Открыть карточку", "open"),
            ("Открыть инвентарь", "inventory"),
            ("Копировать токен", "copy"),
            ("Показать картинку", "portrait"),
            ("Показать токен" if self.token.hidden else "Скрыть токен",
             "show" if self.token.hidden else "hide"),
            ("Оживить" if self.token.dead else "Убить", "revive" if self.token.dead else "kill"),
            ("Удалить токен", "delete"),
        ]:
            if name in {"kill", "revive"} and self.token.actor_id is None:
                continue
            action = menu.addAction(label)
            action.setData(name)
            if name == "inventory":
                action.setIcon(icon("inventory"))
                action.setEnabled(self.has_inventory)
            elif name == "portrait":
                action.setEnabled(not self.token.hidden)
            elif name in {"hide", "show"}:
                action.setIcon(icon("eye_off" if name == "hide" else "eye"))
            elif name in {"kill", "revive"}:
                action.setIcon(icon("token_dead"))
        token_id = self.token.id
        event.accept()
        chosen = menu.exec(event.screenPos())
        if isValid(view) and chosen:
            view.token_action.emit(token_id, chosen.data())


class RasterObjectItem(QGraphicsItem):
    def __init__(self, value, layer, view, path, root, provider):
        super().__init__()
        self.view = view
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, view.role != "player")
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
            self.view.transient_changed.emit("object", self.value.id, self.x(), self.y())

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
        if self.view.role != "editor":
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
