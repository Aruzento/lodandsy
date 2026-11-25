import math

from PySide6.QtCore import QEvent, QPointF, QRectF, QSettings, Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QMenu,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.application.fog_geometry import state_path
from lodandsy.domain.map_document import resolve_token
from lodandsy.domain.map_fog import FogState
from lodandsy.ui.icons import icon
from lodandsy.ui.map_annotations import GridLayer, RasterObjectItem, TokenItem
from lodandsy.ui.project_tree_model import ENTITY_MIME_TYPE


class TileLayer(QGraphicsItem):
    def __init__(self, pyramid, tiles, view):
        super().__init__()
        self.pyramid, self.tiles = pyramid, tiles
        self.view = view
        self.last_tile_count = 0
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(-1000000)

    def boundingRect(self):
        return QRectF(0, 0, self.pyramid.width, self.pyramid.height)

    def paint(self, painter, option, widget=None):
        rect = option.exposedRect.intersected(self.boundingRect()).intersected(
            self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        )
        self.last_tile_count = 0
        zoom = max(0.000001, abs(painter.deviceTransform().m11()))
        level = max(
            0, min(self.pyramid.max_level, self.pyramid.max_level + math.ceil(math.log2(zoom)))
        )
        factor = 2 ** (self.pyramid.max_level - level)
        span = 256 * factor
        while (
            level > 0
            and (math.ceil(rect.width() / span) + 1) * (math.ceil(rect.height() / span) + 1) > 128
        ):
            level -= 1
            factor *= 2
            span *= 2
        for y in range(
            max(0, int(rect.top() // span)),
            min(math.ceil(self.pyramid.height / span), math.ceil(rect.bottom() / span)),
        ):
            for x in range(
                max(0, int(rect.left() // span)),
                min(math.ceil(self.pyramid.width / span), math.ceil(rect.right() / span)),
            ):
                image = self.tiles.get(self.pyramid.tile_path(level, x, y))
                self.last_tile_count += 1
                target = QRectF(x * span, y * span, span, span)
                if image is None:
                    painter.fillRect(target, QColor("#202020"))
                else:
                    target.setWidth(min(image.width() * factor, self.pyramid.width - x * span))
                    target.setHeight(min(image.height() * factor, self.pyramid.height - y * span))
                    painter.drawImage(target, image)


class MapView(QGraphicsView):
    camera_changed = Signal(object)
    transient_changed = Signal(str, str, float, float)
    fullscreen_requested = Signal()
    exit_fullscreen_requested = Signal()
    world_clicked = Signal(float, float)
    object_moved = Signal(str, float, float)
    object_action = Signal(str, str)
    card_dropped = Signal(str, float, float)
    token_moved = Signal(str, float, float)
    measurement_changed = Signal(object)
    token_action = Signal(str, str)
    token_selected = Signal(str)
    token_add_requested = Signal(float, float)
    tool_changed = Signal(str)

    def __init__(self, role="viewer"):
        super().__init__()
        if role not in {"viewer", "editor", "player"}:
            raise ValueError("Unsupported map view role")
        self.role = role
        self._background = None
        self._display_ready = False
        self._model_ready = False
        self._source_rect = QRectF()
        self._fog_state = FogState()
        self._fog_path = QPainterPath()
        self._fog_preview = QPainterPath()
        self._fog_vertices = ()
        self._fog_snap = False
        self.vector_shapes = ()
        self.vector_portals = ()
        self.measurement = None
        self.measurement_mode = QSettings().value("maps/measurement", "grid")
        if self.measurement_mode not in {"grid", "geometry"}:
            self.measurement_mode = "grid"
        self._fog_selection = QPainterPath()
        self.fog_opacity = 0.5
        self.tool = "select"
        self._previous_tool = None
        self.setScene(QGraphicsScene(self))
        if role == "player":
            self.scene().setBackgroundBrush(Qt.GlobalColor.black)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.map_width, self.map_height = 1000, 700
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setAccessibleName("Карта: колесо — масштаб, перетаскивание — перемещение")
        self.setAcceptDrops(role != "player")
        self.card_exists = lambda key: False
        self._background = None
        self._tokens = []
        self._objects = {}
        self._grid = None
        self.scene().selectionChanged.connect(self._selection_changed)
        if role == "player":
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setInteractive(False)
            self.setFrameShape(QGraphicsView.Shape.NoFrame)

    def paintEvent(self, event):
        if self.role == "player" and not self._display_ready:
            painter = QPainter(self.viewport())
            painter.fillRect(self.viewport().rect(), Qt.GlobalColor.black)
            painter.end()
            return
        super().paintEvent(event)

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self._paint_measurement(painter)
        color = QColor("#000000")
        color.setAlphaF(1 if self.role == "player" else self.fog_opacity)
        painter.setBrush(color)
        pen = QPen(color, 2 if self.role == "player" else 0)
        pen.setCosmetic(True)
        painter.setPen(pen if self.role == "player" else Qt.PenStyle.NoPen)
        painter.drawPath(self._fog_path)
        if self.role != "player":
            painter.setPen(QPen(QColor("#dededb"), 0))
            painter.setBrush(QColor(180, 180, 180, 50))
            painter.drawPath(self._fog_preview)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._fog_selection)
            # Overlay geometry is in logical viewport pixels, independent of map zoom/DPR.
            transform = painter.worldTransform()
            painter.resetTransform()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            for index, vertex in enumerate(self._fog_vertices):
                center = transform.map(QPointF(*vertex))
                snap = index == 0 and self._fog_snap
                painter.setPen(QPen(QColor("#ffffff"), 1.5))
                painter.setBrush(QColor("#73d6b2" if snap else "#303030"))
                radius = 7 if snap else 4
                painter.drawEllipse(center, radius, radius)
        painter.restore()
        from lodandsy.ui.map_vectors import paint_vectors

        paint_vectors(self, painter)
        if self.role == "player":
            outside = QPainterPath()
            outside.addRect(rect)
            visible = QPainterPath()
            visible.addRect(self._source_rect)
            painter.fillPath(outside.subtracted(visible), Qt.GlobalColor.black)

    def public_motion_visible(self, item, origin, target):
        from PySide6.QtGui import QPainterPathStroker

        segment = QPainterPath(QPointF(*origin))
        segment.lineTo(QPointF(*target))
        stroke = QPainterPathStroker()
        stroke.setWidth(max(item.boundingRect().width(), item.boundingRect().height()))
        corridor = stroke.createStroke(segment)
        for point in (origin, target):
            corridor.addRect(item.boundingRect().translated(QPointF(*point)))
        return not self._fog_path.intersects(corridor)

    def _paint_measurement(self, painter):
        if self.measurement is None:
            return
        from lodandsy.domain.map_measurements import distance

        key, origin, target = self.measurement
        item = next((i for i in self._tokens if i.token.id == key), None)
        if item is None or not item.isVisible():
            return
        segment = QPainterPath(QPointF(*origin))
        segment.lineTo(QPointF(*target))
        if self.role == "player" and not self.public_motion_visible(item, origin, target):
            return
        value = distance(self.grid, origin, target, self.measurement_mode)
        text = (
            "Масштаб не задан" if value is None else f"{value:.1f}".rstrip("0").rstrip(".") + " фт."
        )
        text += " · сетка" if self.measurement_mode == "grid" else " · геометрия"
        transform = painter.worldTransform()
        start, end = transform.map(QPointF(*origin)), transform.map(QPointF(*target))
        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#eeeeee"), 2))
        painter.drawLine(start, end)
        painter.drawEllipse(start, 4, 4)
        delta = end - start
        angle = math.atan2(delta.y(), delta.x())
        for offset in (-0.45, 0.45):
            painter.drawLine(
                end, end - QPointF(math.cos(angle + offset) * 10, math.sin(angle + offset) * 10)
            )
        label = painter.fontMetrics().boundingRect(text).adjusted(-6, -4, 6, 4)
        footprint = transform.mapRect(item.boundingRect())
        radius = max(footprint.width(), footprint.height()) / 2
        length = math.hypot(delta.x(), delta.y())
        normal = QPointF(delta.y() / length, -delta.x() / length) if length > 0 else QPointF(0, -1)
        if normal.y() > 0:
            normal = -normal
        spacing = (
            radius + abs(normal.x()) * label.width() / 2 + abs(normal.y()) * label.height() / 2 + 12
        )
        label.moveCenter(((start + end) / 2 + normal * spacing).toPoint())
        bounds = self.viewport().rect().adjusted(2, 2, -2, -2)
        if not bounds.contains(label):
            label.moveCenter(((start + end) / 2 - normal * spacing).toPoint())
        label.moveLeft(max(bounds.left(), min(label.left(), bounds.right() - label.width())))
        label.moveTop(max(bounds.top(), min(label.top(), bounds.bottom() - label.height())))
        painter.fillRect(label, QColor("#202020"))
        painter.drawText(label, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def viewportEvent(self, event):
        if self.role == "player" and event.type() == QEvent.Type.ToolTip:
            return True
        return super().viewportEvent(event)

    def _publish_camera(self):
        if getattr(self, "role", None) == "viewer" and self._background is not None:
            self.camera_changed.emit(self.mapToScene(self.viewport().rect()).boundingRect())

    def follow_camera(self, rect):
        if self.role != "player" or rect.isEmpty():
            return
        self._source_rect = QRectF(rect)
        self.setSceneRect(rect)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._display_ready = self._background is not None and self._model_ready
        self.viewport().update()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self._publish_camera()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "role", None) == "player" and not self._source_rect.isEmpty():
            self.follow_camera(self._source_rect)
        else:
            self._publish_camera()

    def fitInView(self, *args):
        super().fitInView(*args)
        self._publish_camera()

    def mouseDoubleClickEvent(self, event):
        if self.role == "player":
            self.fullscreen_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def set_pyramid(self, pyramid, tiles):
        if self._background is not None:
            self.scene().removeItem(self._background)
        self._background = TileLayer(pyramid, tiles, self)
        self.scene().addItem(self._background)
        self.map_width, self.map_height = pyramid.width, pyramid.height
        tiles.ready.connect(self.viewport().update)
        self.scene().setSceneRect(QRectF(0, 0, self.map_width, self.map_height))
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        if self.role == "player":
            self.follow_camera(self._source_rect)

    def set_annotations(
        self,
        document,
        card_resolver,
        root,
        assets,
        provider,
        *,
        fog_path=None,
        participant_resolver=None,
    ):
        if self.role == "player":
            self._display_ready = False
        if self._fog_state != document.fog or fog_path is not None:
            self._fog_path = fog_path if fog_path is not None else state_path(document.fog)
            self._fog_state = document.fog
        self.vector_shapes = document.shapes
        self.vector_portals = document.portals if self.role != "player" else ()
        self.grid = document.grid
        previous = {item.token.id: item for item in self._tokens}
        current_ids = {token.id for token in document.tokens}
        for key in previous.keys() - current_ids:
            self.scene().removeItem(previous[key])
        rect = QRectF(0, 0, self.map_width, self.map_height)
        if self._grid is None or self._grid.grid != document.grid or self._grid.rect != rect:
            if self._grid is not None:
                self.scene().removeItem(self._grid)
            self._grid = GridLayer(document.grid, self)
            self.scene().addItem(self._grid)
        items = []
        for token in document.tokens:
            try:
                card = card_resolver(token.card_id)
            except ValueError:
                card = None
            presentation = resolve_token(token, card)
            if self.role != "player" and token.actor_id and participant_resolver:
                from dataclasses import replace

                name, summary, inventory = participant_resolver(token.card_id, token.actor_id)
                presentation = replace(
                    presentation, label=token.label_override or name, summary=summary
                )
            asset = assets.get(presentation.asset_id)
            path = asset.path if asset else None

            item = previous.get(token.id)
            if item is None:
                item = TokenItem(token, presentation, self, root, path, provider)
                self.scene().addItem(item)
            elif (
                item.token != token
                or item.root != root
                or item.asset_path != path
                or item.presentation != presentation
                or item.cell_size != document.grid.cell_size
                or bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
                != (self._background is not None and self.role == "viewer")
            ):
                item.set_value(token, presentation, root, path, provider)
            items.append(item)
        self._tokens = items

        layers = {layer.id: layer for layer in document.layers}
        for item in items:
            item.setVisible(item.token.layer_id is None or layers[item.token.layer_id].visible)
            item.setAcceptedMouseButtons(
                Qt.MouseButton.NoButton
                if self.role != "viewer"
                else Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
            )
        ids = {o.id for o in document.objects}
        for key in self._objects.keys() - ids:
            self.scene().removeItem(self._objects.pop(key))
        for value in document.objects:
            layer = layers[value.layer_id]
            asset = assets.get(value.asset_id)
            path = asset.path if asset else None
            if value.id in self._objects:
                self._objects[value.id].set_value(value, layer, path, root, provider)
            else:
                item = RasterObjectItem(value, layer, self, path, root, provider)
                self.scene().addItem(item)
                self._objects[value.id] = item

        self._model_ready = True
        if self.role == "player":
            self.follow_camera(self._source_rect)
        if self.role != "player":
            bounds = QRectF(0, 0, self.map_width, self.map_height)
            for item in (*self._tokens, *self._objects.values()):
                if item.isVisible():
                    bounds = bounds.united(item.sceneBoundingRect())
            self.scene().setSceneRect(bounds)
        self.viewport().update()

    def _selection_changed(self):
        if self.role == "player":
            return
        for item in self.scene().selectedItems():
            if isinstance(item, TokenItem):
                self.token_selected.emit(item.token.id)
                break

    def select_token(self, token_id):
        for item in self._tokens:
            item.setSelected(item.token.id == token_id)
            if item.token.id == token_id:
                self.centerOn(item)

    def selected_token_id(self):
        return next(
            (item.token.id for item in self.scene().selectedItems() if isinstance(item, TokenItem)),
            None,
        )

    def refresh_participant(self, card_id, actor_id, resolver):
        if self.role == "player":
            return
        from dataclasses import replace

        name, summary, inventory = resolver(card_id, actor_id)
        for item in self._tokens:
            if item.token.card_id == card_id and item.token.actor_id == actor_id:
                presentation = replace(
                    item.presentation, label=item.token.label_override or name, summary=summary
                )
                item.set_value(item.token, presentation, item.root, item.asset_path, item.provider)

    def _drag_card(self, event):
        if (
            self.role != "viewer"
            or self._background is None
            or not event.mimeData().hasFormat(ENTITY_MIME_TYPE)
        ):
            return None
        try:
            key = bytes(event.mimeData().data(ENTITY_MIME_TYPE)).decode("utf-8")
        except UnicodeDecodeError:
            return None
        return key if self.card_exists(key) else None

    def dragEnterEvent(self, event):
        if self._drag_card(event):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        key = self._drag_card(event)
        point = self.mapToScene(event.position().toPoint())
        if key and 0 <= point.x() <= self.map_width and 0 <= point.y() <= self.map_height:
            self.card_dropped.emit(key, point.x(), point.y())
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def set_tool(self, name):
        if self.role != "editor" or name not in {"select", "pan", "place"}:
            return
        self.tool = name
        self.setDragMode(
            QGraphicsView.DragMode.ScrollHandDrag
            if name == "pan"
            else QGraphicsView.DragMode.RubberBandDrag
        )
        for item in self._objects.values():
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                name == "select" and self._background is not None,
            )
        self.viewport().setCursor(
            Qt.CursorShape.OpenHandCursor
            if name == "pan"
            else Qt.CursorShape.CrossCursor
            if name == "place"
            else Qt.CursorShape.ArrowCursor
        )
        self.tool_changed.emit(name)

    def mousePressEvent(self, event):
        if self.role == "player":
            self.setFocus()
            event.accept()
            return
        if (
            self.role == "editor"
            and self.tool == "place"
            and event.button() == Qt.MouseButton.LeftButton
        ):
            point = self.mapToScene(event.position().toPoint())
            if (
                self._background is not None
                and 0 <= point.x() <= self.map_width
                and 0 <= point.y() <= self.map_height
            ):
                self.world_clicked.emit(point.x(), point.y())
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if self.role == "player":
            if event.key() == Qt.Key.Key_F11:
                self.fullscreen_requested.emit()
            elif event.key() == Qt.Key.Key_Escape:
                self.exit_fullscreen_requested.emit()
            event.accept()
            return
        if self.role == "editor" and event.key() == Qt.Key.Key_Space:
            if not event.isAutoRepeat() and self._previous_tool is None:
                self._previous_tool = self.tool
                self.set_tool("pan")
            event.accept()
            return
        if self.role == "viewer" and event.key() == Qt.Key.Key_Escape:
            self.measurement_changed.emit(None)
            for item in self._tokens:
                if getattr(item, "_dragging", False):
                    item._cancelled = True
                    item.setPos(item._drag_origin)
                    self.transient_changed.emit("token", item.token.id, item.x(), item.y())
            event.accept()
            return
        if self.role == "editor" and event.key() == Qt.Key.Key_Escape:
            for item in self._objects.values():
                if getattr(item, "_dragging", False):
                    item.setPos(item._origin)
                    item._cancelled = True
                    self.transient_changed.emit("object", item.value.id, item.x(), item.y())
            self.scene().clearSelection()
            self.set_tool("select")
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and self._previous_tool is not None:
            if not event.isAutoRepeat():
                tool, self._previous_tool = self._previous_tool, None
                self.set_tool(tool)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self.measurement_changed.emit(None)
        if self._previous_tool is not None:
            tool, self._previous_tool = self._previous_tool, None
            self.set_tool(tool)
        super().focusOutEvent(event)

    def wheelEvent(self, event):
        if self.role == "player":
            event.accept()
            return
        scale = self.transform().m11()
        target = max(
            self.minimum_zoom(), min(16, scale * (1.2 if event.angleDelta().y() > 0 else 1 / 1.2))
        )
        self.scale(target / scale, target / scale)
        self._publish_camera()
        event.accept()

    def contextMenuEvent(self, event):
        if self.role == "player":
            event.accept()
            return
        item = self.itemAt(event.pos())
        while item is not None and not isinstance(item, (TokenItem, RasterObjectItem)):
            item = item.parentItem()
        if item is not None and (isinstance(item, TokenItem) or self.role == "editor"):
            super().contextMenuEvent(event)
            return
        if self.role == "editor":
            return
        point = self.mapToScene(event.pos())
        if 0 <= point.x() <= self.map_width and 0 <= point.y() <= self.map_height:
            menu = QMenu(self)
            token = menu.addAction("Добавить токен…")
            token.setEnabled(self._background is not None)
            selected = menu.exec(event.globalPos())
            if selected == token:
                self.token_add_requested.emit(point.x(), point.y())

    def camera(self):
        center = self.mapToScene(self.viewport().rect().center())
        return {
            "x": center.x() / self.map_width,
            "y": center.y() / self.map_height,
            "zoom": self.transform().m11(),
        }

    def minimum_zoom(self):
        bounds = self.sceneRect().united(QRectF(0, 0, self.map_width, self.map_height))
        fit = min(
            max(1, self.viewport().width()) / max(1, bounds.width()),
            max(1, self.viewport().height()) / max(1, bounds.height()),
        )
        return max(1e-8, min(0.01, fit / 16))

    def restore_camera(self, state):
        values = [state.get(key) for key in ["x", "y", "zoom"]]
        if not all(type(value) in (int, float) and math.isfinite(value) for value in values):
            return
        x, y, zoom = values
        self.resetTransform()
        self.scale(max(self.minimum_zoom(), min(16, zoom)), max(self.minimum_zoom(), min(16, zoom)))
        bounds = self.sceneRect().united(QRectF(0, 0, self.map_width, self.map_height))
        self.centerOn(
            QPointF(
                max(bounds.left(), min(bounds.right(), x * self.map_width)),
                max(bounds.top(), min(bounds.bottom(), y * self.map_height)),
            )
        )
        self._publish_camera()


class MapWidget(QWidget):
    grid_requested = Signal()
    editor_requested = Signal()
    presentation_requested = Signal()

    def __init__(self, undo_stack):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        buttons = QToolBar(self)
        buttons.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.token_add = QAction(icon("plus"), "Токен", self)
        self.token_add.setEnabled(False)
        grid = QAction(icon("table"), "Сетка", self)
        grid.triggered.connect(self.grid_requested)
        fit = QAction(icon("fit"), "Вся карта", self)
        editor = QAction(icon("rename"), "Редактор", self)
        editor.triggered.connect(self.editor_requested)
        buttons.addActions([self.token_add, grid, fit, editor])
        presentation = QAction(icon("monitor"), "Открыть презентацию", self)
        presentation.triggered.connect(self.presentation_requested)
        button = QToolButton(buttons)
        button.setDefaultAction(presentation)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        buttons.addWidget(button)
        buttons.addSeparator()
        self.add_undo_actions(buttons, undo_stack)
        layout.addWidget(buttons)
        self.message = QLabel("Загрузка изображения…")
        self.message.setWordWrap(True)
        self.message.setObjectName("mapStatus")
        layout.addWidget(self.message)
        self.view = MapView()
        from lodandsy.ui.fog_tools import FogTools

        self.fog_tools = FogTools(self.view, self)
        metric = QAction("Дистанция: геометрия", self)
        metric.setCheckable(True)
        metric.setChecked(self.view.measurement_mode == "geometry")
        metric.setToolTip("Без snap используется непрерывная метрика; сетка — диагональ за клетку")

        def set_metric(checked):
            self.view.measurement_mode = "geometry" if checked else "grid"
            QSettings().setValue("maps/measurement", self.view.measurement_mode)
            self.view.viewport().update()

        metric.toggled.connect(set_metric)
        buttons.addAction(metric)
        fog = QAction(icon("fog"), "Туман войны", self)
        fog.setCheckable(True)
        fog.toggled.connect(self.fog_tools.setVisible)
        fog_button = QToolButton(buttons)
        fog_button.setDefaultAction(fog)
        fog_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        buttons.addWidget(fog_button)
        from lodandsy.ui.map_vectors import VectorTools

        self.vector_tools = VectorTools(self.view, self)
        self.vector_tools.hide()
        vectors = QAction(icon("vector"), "Фигуры и порталы", self)
        vectors.setCheckable(True)
        vectors.toggled.connect(self.vector_tools.setVisible)
        vectors.toggled.connect(
            lambda checked: self.fog_tools.hide() if checked else self.vector_tools.cancel()
        )
        fog.toggled.connect(lambda checked: self.vector_tools.hide() if checked else None)
        buttons.addAction(vectors)
        layout.addWidget(self.vector_tools)
        layout.addWidget(self.fog_tools)
        layout.addWidget(self.view, 1)
        self.pending_camera = None
        self.project_root = None
        fit.triggered.connect(
            lambda: self.view.fitInView(self.view.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        )

    def add_undo_actions(self, bar, stack):
        for name, shortcut, action in [
            ("undo", "Ctrl+Z", stack.createUndoAction(self, "Отменить")),
            ("redo", "Ctrl+Y", stack.createRedoAction(self, "Повторить")),
        ]:
            action.setIcon(icon(name))
            action.setShortcut(shortcut)

            def update_tip(a=action, key=shortcut):
                text = a.text() + " · " + key
                if a.toolTip() != text:
                    a.setToolTip(text)

            action.changed.connect(update_tip)
            update_tip()
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.addAction(action)
            button = QToolButton(bar)
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setAccessibleName("Отменить" if name == "undo" else "Повторить")
            bar.addWidget(button)

    def image_ready(self, root, _name):
        if root == self.project_root:
            self.view.viewport().update()

    def camera_state(self):
        if self.pending_camera is not None:
            return self.pending_camera
        return self.view.camera() if self.view._background is not None else None

    def restore_camera_state(self, state):
        if self.view._background is None:
            self.pending_camera = state
        else:
            self.view.restore_camera(state)
            self.pending_camera = None
