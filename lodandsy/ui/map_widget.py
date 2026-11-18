import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen, QPixmap
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


class PinItem(QGraphicsEllipseItem):
    def __init__(self, pin, view, broken):
        super().__init__(-7, -7, 14, 14)
        self.pin_id, self.view = pin.id, view
        self.setBrush(QColor("#d97575" if broken else "#c5a35c"))
        self.setPen(QPen(QColor("#101827"), 2))
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setToolTip(pin.title + (" · Разорванная ссылка" if broken else ""))
        self.setZValue(1)
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

    def set_image(self, image):
        if self._background is not None:
            self.scene().removeItem(self._background)
        self._background = self.scene().addPixmap(QPixmap.fromImage(image))
        self.map_width, self.map_height = image.width(), image.height()
        self._background.setZValue(-1)
        self.scene().setSceneRect(QRectF(0, 0, self.map_width, self.map_height))
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def set_pins(self, pins, existing_cards):
        for item in self._pins:
            self.scene().removeItem(item)
        self._pins.clear()
        for pin in pins:
            item = PinItem(pin, self, pin.card_id is not None and pin.card_id not in existing_cards)
            item.setPos(pin.x * self.map_width, pin.y * self.map_height)
            self.scene().addItem(item)
            self._pins.append(item)

    def wheelEvent(self, event):
        scale = self.transform().m11()
        target = max(0.01, min(16, scale * (1.2 if event.angleDelta().y() > 0 else 1 / 1.2)))
        self.scale(target / scale, target / scale)
        event.accept()

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        while item is not None and not isinstance(item, PinItem):
            item = item.parentItem()
        if item is not None:
            super().contextMenuEvent(event)
            return
        point = self.mapToScene(event.pos())
        if 0 <= point.x() <= self.map_width and 0 <= point.y() <= self.map_height:
            menu = QMenu(self)
            add = menu.addAction("Добавить маркер…")
            if menu.exec(event.globalPos()) == add:
                self.add_requested.emit(point.x() / self.map_width, point.y() / self.map_height)

    def camera(self):
        center = self.mapToScene(self.viewport().rect().center())
        return {"x": center.x() / self.map_width, "y": center.y() / self.map_height,
                "zoom": self.transform().m11()}

    def restore_camera(self, state):
        values = [state.get(key) for key in ["x", "y", "zoom"]]
        if not all(type(value) in (int, float) and math.isfinite(value) for value in values):
            return
        x, y, zoom = values
        self.resetTransform()
        self.scale(max(0.01, min(16, zoom)), max(0.01, min(16, zoom)))
        self.centerOn(QPointF(max(0, min(1, x)) * self.map_width,
                             max(0, min(1, y)) * self.map_height))


class MapWidget(QWidget):
    rename_requested = Signal()
    delete_requested = Signal()

    def __init__(self, undo_stack):
        super().__init__()
        layout = QVBoxLayout(self)
        buttons = QToolBar(self)
        buttons.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.add = QAction(icon("plus"), "Маркер", self)
        self.add.setToolTip("Добавить маркер в центре карты")
        fit = QAction(icon("fit"), "Вся карта", self)
        rename = QAction(icon("rename"), "Название", self)
        delete = QAction(icon("delete"), "Удалить карту", self)
        buttons.addActions([self.add, fit, rename, delete])
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
        fit.triggered.connect(lambda: self.view.fitInView(
            self.view.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio))
        rename.triggered.connect(self.rename_requested)
        delete.triggered.connect(self.delete_requested)
