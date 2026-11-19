import math
from html import escape

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QLabel,
    QMenu,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from lodandsy.ui.icons import icon
from lodandsy.ui.map_annotations import GridLayer, TokenItem


class TileLayer(QGraphicsItem):
    def __init__(self, pyramid, tiles, view):
        super().__init__()
        self.pyramid, self.tiles = pyramid, tiles
        self.view = view
        self.last_tile_count = 0
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(-1)

    def boundingRect(self):
        return QRectF(0, 0, self.pyramid.width, self.pyramid.height)

    def paint(self, painter, option, widget=None):
        rect = option.exposedRect.intersected(self.boundingRect()).intersected(
            self.view.mapToScene(self.view.viewport().rect()).boundingRect())
        self.last_tile_count = 0
        zoom = max(.000001, abs(painter.deviceTransform().m11()))
        level = max(0, min(self.pyramid.max_level,
                           self.pyramid.max_level + math.ceil(math.log2(zoom))))
        factor = 2 ** (self.pyramid.max_level - level)
        span = 256 * factor
        while level > 0 and (math.ceil(rect.width() / span) + 1) * (
                math.ceil(rect.height() / span) + 1) > 128:
            level -= 1
            factor *= 2
            span *= 2
        for y in range(max(0, int(rect.top() // span)),
                       min(math.ceil(self.pyramid.height / span), math.ceil(rect.bottom() / span))):
            for x in range(max(0, int(rect.left() // span)),
                           min(math.ceil(self.pyramid.width / span),
                               math.ceil(rect.right() / span))):
                image = self.tiles.get(self.pyramid.tile_path(level, x, y))
                self.last_tile_count += 1
                target = QRectF(x * span, y * span, span, span)
                if image is None:
                    painter.fillRect(target, QColor("#182437"))
                else:
                    target.setWidth(min(image.width() * factor, self.pyramid.width - x * span))
                    target.setHeight(min(image.height() * factor, self.pyramid.height - y * span))
                    painter.drawImage(target, image)


class PinItem(QGraphicsEllipseItem):
    def __init__(self, pin, view, broken):
        super().__init__(-7, -7, 14, 14)
        self.pin_id, self.view = pin.id, view
        self.setBrush(QColor("#d97575" if broken else "#c5a35c"))
        self.setPen(QPen(QColor("#101827"), 2))
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setToolTip("<qt>" + escape(pin.title
                                       + (" · Разорванная ссылка" if broken else "")) + "</qt>")
        self.setZValue(20000)  # Keep M1 pins accessible above graphical tokens.
        label = QGraphicsSimpleTextItem(pin.title, self)
        label.setPos(10, -10)
        label.setBrush(QColor("#f4e7c7"))
        label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        label.setZValue(2)
        background = QGraphicsRectItem(label.boundingRect().adjusted(-3, -1, 3, 1), self)
        background.setPos(label.pos())
        background.setBrush(QColor("#101b2c"))
        background.setPen(QPen(QColor("#38465c")))
        background.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        point = self.pos()
        x = max(0.0, min(1.0, point.x() / self.view.map_width))
        y = max(0.0, min(1.0, point.y() / self.view.map_height))
        self.setPos(x * self.view.map_width, y * self.view.map_height)
        view, pin_id = self.view, self.pin_id
        QTimer.singleShot(0, view, lambda: view.pin_moved.emit(pin_id, x, y))

    def mouseDoubleClickEvent(self, event):
        self.view.pin_action.emit(self.pin_id, "open")
        event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu()
        for title, action in [("Открыть карточку", "open"), ("Переименовать маркер…", "rename"),
                              ("Связать с карточкой…", "link"),
                              ("Создать связанную карточку…", "create"),
                              ("Убрать связь", "unlink"), ("Удалить маркер", "delete")]:
            item = menu.addAction(title)
            item.setData(action)
        chosen = menu.exec(event.screenPos())
        if chosen:
            self.view.pin_action.emit(self.pin_id, chosen.data())
        event.accept()


class MapView(QGraphicsView):
    token_moved = Signal(str, float, float)
    token_action = Signal(str, str)
    token_add_requested = Signal(float, float)
    pin_moved = Signal(str, float, float)
    pin_action = Signal(str, str)
    add_requested = Signal(float, float)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.map_width, self.map_height = 1000, 700
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setAccessibleName("Карта: колесо — масштаб, перетаскивание — перемещение")
        self._background = None
        self._pins = []
        self._tokens = []
        self._grid = None
        self._pin_state = None

    def set_pyramid(self, pyramid, tiles):
        if self._background is not None:
            self.scene().removeItem(self._background)
        self._background = TileLayer(pyramid, tiles, self)
        self.scene().addItem(self._background)
        self.map_width, self.map_height = pyramid.width, pyramid.height
        tiles.ready.connect(self.viewport().update)
        self.scene().setSceneRect(QRectF(0, 0, self.map_width, self.map_height))
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def set_pins(self, pins, existing_cards):
        state = pins, frozenset(existing_cards), self.map_width, self.map_height
        if self._pin_state == state:
            return
        self._pin_state = state
        for item in self._pins:
            self.scene().removeItem(item)
        self._pins.clear()
        for pin in pins:
            item = PinItem(pin, self, pin.card_id is not None and pin.card_id not in existing_cards)
            item.setPos(pin.x * self.map_width, pin.y * self.map_height)
            self.scene().addItem(item)
            self._pins.append(item)

    def set_annotations(self, document, existing_cards, root, assets, provider):
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
            asset = assets.get(token.asset_id)
            path = asset.path if asset else None
            broken = token.card_id is not None and token.card_id not in existing_cards
            item = previous.get(token.id)
            if item is None:
                item = TokenItem(token, self, root, path, provider, broken)
                self.scene().addItem(item)
            elif (item.token != token or item.root != root or item.asset_path != path
                  or item.broken != broken or bool(item.flags()
                  & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
                  != (self._background is not None)):
                item.set_value(token, root, path, provider, broken)
            items.append(item)
        self._tokens = items
        if self._background is None:
            self.scene().setSceneRect(self.scene().itemsBoundingRect().united(
                QRectF(0, 0, self.map_width, self.map_height)))

    def wheelEvent(self, event):
        scale = self.transform().m11()
        target = max(self.minimum_zoom(), min(
            16, scale * (1.2 if event.angleDelta().y() > 0 else 1 / 1.2)))
        self.scale(target / scale, target / scale)
        event.accept()

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        while item is not None and not isinstance(item, (PinItem, TokenItem)):
            item = item.parentItem()
        if item is not None:
            super().contextMenuEvent(event)
            return
        point = self.mapToScene(event.pos())
        if 0 <= point.x() <= self.map_width and 0 <= point.y() <= self.map_height:
            menu = QMenu(self)
            add = menu.addAction("Добавить маркер…")
            token = menu.addAction("Добавить токен…")
            token.setEnabled(self._background is not None)
            selected = menu.exec(event.globalPos())
            if selected == add:
                self.add_requested.emit(point.x() / self.map_width, point.y() / self.map_height)
            elif selected == token:
                self.token_add_requested.emit(point.x(), point.y())

    def camera(self):
        center = self.mapToScene(self.viewport().rect().center())
        return {"x": center.x() / self.map_width, "y": center.y() / self.map_height,
                "zoom": self.transform().m11()}

    def minimum_zoom(self):
        fit = min(max(1, self.viewport().width()) / self.map_width,
                  max(1, self.viewport().height()) / self.map_height)
        return max(1e-8, min(.01, fit / 16))

    def restore_camera(self, state):
        values = [state.get(key) for key in ["x", "y", "zoom"]]
        if not all(type(value) in (int, float) and math.isfinite(value) for value in values):
            return
        x, y, zoom = values
        self.resetTransform()
        self.scale(max(self.minimum_zoom(), min(16, zoom)),
                   max(self.minimum_zoom(), min(16, zoom)))
        self.centerOn(QPointF(max(0, min(1, x)) * self.map_width,
                             max(0, min(1, y)) * self.map_height))


class MapWidget(QWidget):
    grid_requested = Signal()
    rename_requested = Signal()
    delete_requested = Signal()

    def __init__(self, undo_stack):
        super().__init__()
        layout = QVBoxLayout(self)
        buttons = QToolBar(self)
        buttons.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.add = QAction(icon("plus"), "Маркер", self)
        self.add.setToolTip("Добавить маркер в центре карты")
        self.token_add = QAction(icon("plus"), "Токен", self)
        self.token_add.setToolTip("Добавить токен с изображением в центре видимой области")
        self.token_add.setEnabled(False)
        grid = QAction("Сетка…", self)
        grid.setToolTip("Квадратная сетка, размер, смещение, прозрачность и snap")
        grid.triggered.connect(self.grid_requested)
        fit = QAction(icon("fit"), "Вся карта", self)
        rename = QAction(icon("rename"), "Название", self)
        delete = QAction(icon("delete"), "Удалить карту", self)
        buttons.addActions([self.add, self.token_add, grid, fit, rename, delete])
        layout.addWidget(buttons)
        undo = undo_stack.createUndoAction(self, "Отменить")
        redo = undo_stack.createRedoAction(self, "Повторить")
        for action, shortcut in [(undo, "Ctrl+Z"), (redo, "Ctrl+Y")]:
            action.setShortcut(shortcut)
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.addAction(action)
            buttons.addAction(action)
        self.message = QLabel("Загрузка изображения…")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.view = MapView()
        layout.addWidget(self.view, 1)
        self.pending_camera = None
        self.project_root = None
        fit.triggered.connect(lambda: self.view.fitInView(
            self.view.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio))
        rename.triggered.connect(self.rename_requested)
        delete.triggered.connect(self.delete_requested)

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
