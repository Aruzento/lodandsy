import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QMenu,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from lodandsy.domain.map_document import resolve_token
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
                    painter.fillRect(target, QColor("#182437"))
                else:
                    target.setWidth(min(image.width() * factor, self.pyramid.width - x * span))
                    target.setHeight(min(image.height() * factor, self.pyramid.height - y * span))
                    painter.drawImage(target, image)


class MapView(QGraphicsView):
    world_clicked = Signal(float, float)
    object_moved = Signal(str, float, float)
    object_action = Signal(str, str)
    card_dropped = Signal(str, float, float)
    token_moved = Signal(str, float, float)
    token_action = Signal(str, str)
    token_add_requested = Signal(float, float)
    tool_changed = Signal(str)

    def __init__(self, role="viewer"):
        super().__init__()
        if role not in {"viewer", "editor"}:
            raise ValueError("Unsupported map view role")
        self.role = role
        self.tool = "select"
        self._previous_tool = None
        self.setScene(QGraphicsScene(self))
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.map_width, self.map_height = 1000, 700
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setAccessibleName("Карта: колесо — масштаб, перетаскивание — перемещение")
        self.setAcceptDrops(True)
        self.card_exists = lambda key: False
        self._background = None
        self._tokens = []
        self._objects = {}
        self._grid = None

    def set_pyramid(self, pyramid, tiles):
        if self._background is not None:
            self.scene().removeItem(self._background)
        self._background = TileLayer(pyramid, tiles, self)
        self.scene().addItem(self._background)
        self.map_width, self.map_height = pyramid.width, pyramid.height
        tiles.ready.connect(self.viewport().update)
        self.scene().setSceneRect(QRectF(0, 0, self.map_width, self.map_height))
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def set_annotations(self, document, card_resolver, root, assets, provider):
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
                if self.role == "editor"
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

        if self._background is None:
            self.scene().setSceneRect(
                self.scene()
                .itemsBoundingRect()
                .united(QRectF(0, 0, self.map_width, self.map_height))
            )

    def _drag_card(self, event):
        if (
            self.role == "editor"
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
        if self.role == "editor" and event.key() == Qt.Key.Key_Space:
            if not event.isAutoRepeat() and self._previous_tool is None:
                self._previous_tool = self.tool
                self.set_tool("pan")
            event.accept()
            return
        if self.role == "editor" and event.key() == Qt.Key.Key_Escape:
            for item in self._objects.values():
                if getattr(item, "_dragging", False):
                    item.setPos(item._origin)
                    item._cancelled = True
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
        if self._previous_tool is not None:
            tool, self._previous_tool = self._previous_tool, None
            self.set_tool(tool)
        super().focusOutEvent(event)

    def wheelEvent(self, event):
        scale = self.transform().m11()
        target = max(
            self.minimum_zoom(), min(16, scale * (1.2 if event.angleDelta().y() > 0 else 1 / 1.2))
        )
        self.scale(target / scale, target / scale)
        event.accept()

    def contextMenuEvent(self, event):
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
        fit = min(
            max(1, self.viewport().width()) / self.map_width,
            max(1, self.viewport().height()) / self.map_height,
        )
        return max(1e-8, min(0.01, fit / 16))

    def restore_camera(self, state):
        values = [state.get(key) for key in ["x", "y", "zoom"]]
        if not all(type(value) in (int, float) and math.isfinite(value) for value in values):
            return
        x, y, zoom = values
        self.resetTransform()
        self.scale(max(self.minimum_zoom(), min(16, zoom)), max(self.minimum_zoom(), min(16, zoom)))
        self.centerOn(
            QPointF(max(0, min(1, x)) * self.map_width, max(0, min(1, y)) * self.map_height)
        )


class MapWidget(QWidget):
    grid_requested = Signal()
    editor_requested = Signal()

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
        buttons.addSeparator()
        self.add_undo_actions(buttons, undo_stack)
        layout.addWidget(buttons)
        self.message = QLabel("Загрузка изображения…")
        self.message.setWordWrap(True)
        self.message.setObjectName("mapStatus")
        layout.addWidget(self.message)
        self.view = MapView()
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
            action.setToolTip(action.text() + " · " + shortcut)
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.addAction(action)
            bar.addAction(action)

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
