"""Maps-owned vector gestures and public foreground painter."""

import math
from dataclasses import dataclass, replace

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QTransform,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from lodandsy.domain.map_document import MAX_TOKEN_EXTENT, MapShape, TokenInstance
from lodandsy.domain.map_measurements import distance
from lodandsy.ui.map_annotations import TokenItem

TOKEN_TRANSFORMS = {"resize_token", "rotate_token"}
TRANSFORM_KEYS = {
    Qt.Key.Key_Alt: Qt.KeyboardModifier.AltModifier,
    Qt.Key.Key_Shift: Qt.KeyboardModifier.ShiftModifier,
}


def mode_is_portal(gesture):
    return gesture[0] == "portal"


def local_path(value):
    path = QPainterPath()
    if value.kind == "circle":
        radius = value.points[0][0]
        path.addEllipse(QPointF(), radius, radius)
    else:
        points = value.points
        if value.kind == "cone":
            length = value.points[0][0]
            points = ((0, 0), (length, -length / 2), (length, length / 2))
        path.moveTo(QPointF(*points[0]))
        for point in points[1:]:
            path.lineTo(QPointF(*point))
        path.closeSubpath()
    return path


def transform(value):
    result = QTransform()
    result.translate(value.x, value.y)
    result.rotate(value.rotation)
    result.scale(value.scale, value.scale)
    return result


def resize_factors(rect, corner, point, modifiers, *, uniform=False, minimum=0.01):
    anchor = (
        rect.center() if modifiers & Qt.KeyboardModifier.ShiftModifier
        else QPointF(
            rect.left() if corner.x() == rect.right() else rect.right(),
            rect.top() if corner.y() == rect.bottom() else rect.bottom(),
        )
    )

    def factor(delta, span):
        if minimum is not None:
            return max(minimum, delta * math.copysign(1, span) / max(minimum, abs(span)))
        if not span:
            raise ValueError("Размер неразличим при текущей точности")
        return delta / span

    sx = factor(point.x() - anchor.x(), corner.x() - anchor.x())
    sy = factor(point.y() - anchor.y(), corner.y() - anchor.y())
    if uniform or modifiers & Qt.KeyboardModifier.AltModifier:
        sx = sy = max(sx, sy)
    return anchor, sx, sy


def rotation_for_drag(angle, center, start, point, modifiers):
    old, new = start - center, point - center
    if new.isNull():
        return angle
    angle += math.degrees(math.atan2(new.y(), new.x()) - math.atan2(old.y(), old.x()))
    angle = (angle + 180) % 360 - 180
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        angle = round(angle / 15) * 15
    return angle


def rotation_handle(view, matrix, rect):
    viewport = view.viewportTransform()
    top = viewport.map(matrix.map(QPointF(rect.center().x(), rect.top())))
    normal = viewport.map(QPointF(-matrix.m21(), -matrix.m22())) - viewport.map(QPointF())
    length = math.hypot(normal.x(), normal.y())
    return viewport.inverted()[0].map(top + normal * (25 / length))


def paint_edit_handles(painter, points, *, frame=None):
    mapping = painter.worldTransform()
    painter.save()
    painter.resetTransform()
    painter.setPen(QPen(QColor("#ffffff"), 1))
    if frame is not None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(QPolygonF([mapping.map(point) for point in frame]))
    painter.setBrush(QColor("#303030"))
    for point in points:
        painter.drawEllipse(mapping.map(point), 5, 5)
    painter.restore()


def resize_corners(rect):
    return rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()


@dataclass(frozen=True)
class TokenTransform:
    item: TokenItem
    token: TokenInstance
    size: tuple[float | int, float | int]
    cell_size: float
    rect: QRectF
    matrix: QTransform

    def is_current(self):
        item = self.item
        return (
            isValid(item) and item.scene() is not None and item.can_transform and item.isSelected()
            and item.token == self.token and item.cell_size == self.cell_size
            and (item.presentation.cells_w, item.presentation.cells_h) == self.size
        )

    def resized(self, corner, delta, modifiers):
        if delta.isNull():
            return self.token
        inverse = self.matrix.inverted()[0]
        local = inverse.map(self.matrix.map(corner) + delta)
        anchor, sx, sy = resize_factors(self.rect, corner, local, modifiers, minimum=None)
        if not all(math.isfinite(factor) and factor > 0 for factor in (sx, sy)):
            raise ValueError("Размер должен быть положительным")
        center = QPointF(self.token.x, self.token.y)
        candidate = self.matrix.map(QPointF(anchor.x() * (1 - sx), anchor.y() * (1 - sy)))
        change = candidate - center
        max_x = max(self.item.view.map_width, center.x())
        max_y = max(self.item.view.map_height, center.y())
        # Interpolate both factors together at the canvas boundary. This keeps
        # the chosen anchor and preserves the ratio in uniform mode.
        fraction = 1.0
        for origin, offset, maximum in (
            (center.x(), change.x(), max_x), (center.y(), change.y(), max_y),
        ):
            if offset < 0 and origin + offset < 0:
                fraction = min(fraction, -origin / offset)
            elif offset > 0 and origin + offset > maximum:
                fraction = min(fraction, (maximum - origin) / offset)
        width = self.size[0] * (1 + (sx - 1) * fraction if fraction < 1 else sx)
        height = self.size[1] * (1 + (sy - 1) * fraction if fraction < 1 else sy)
        if not all(0 < extent / 2 and extent <= MAX_TOKEN_EXTENT
                   for extent in (width * self.cell_size, height * self.cell_size)):
            raise ValueError("Размер токена вне технических пределов карты")
        x = max(0, min(max_x, center.x() + change.x() * fraction))
        y = max(0, min(max_y, center.y() + change.y() * fraction))
        if (width, height, x, y) == (*self.size, self.token.x, self.token.y):
            return self.token
        return replace(self.token, x=x, y=y, cells_w=width, cells_h=height)


def dimensions(value, grid):
    factor = distance(grid, (0, 0), (value.scale, 0), "geometry")
    if factor is None:
        return "Масштаб не задан"

    def number(n):
        return f"{n:.1f}".rstrip("0").rstrip(".")

    if value.kind in {"circle", "cone"}:
        return (
            ("Радиус " if value.kind == "circle" else "Длина ")
            + number(value.points[0][0] * factor)
            + " фт."
        )
    rect = local_path(value).boundingRect()
    text = number(rect.width() * factor) + " × " + number(rect.height() * factor) + " фт."
    if value.kind != "rectangle":
        points = value.points
        perimeter = sum(
            math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(points, (*points[1:], points[0]))
        )
        text += " · периметр " + number(perimeter * factor) + " фт."
    return text


def paint_vectors(view, painter):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    tools = getattr(view, "vector_tools", None) if view.role != "player" else None
    if tools and not tools.enabled:
        tools = None
    shapes = view.vector_shapes
    if tools and tools.preview:
        shapes = tuple(v for v in shapes if v.id != tools.preview.id) + (
            (tools.preview,) if isinstance(tools.preview, MapShape) else ()
        )
    exposed = view.mapToScene(view.viewport().rect()).boundingRect()
    cache = getattr(view, "_vector_render_cache", None)
    if cache is None:
        cache = view._vector_render_cache = {}
    font_key = painter.font().toString()
    for value in shapes:
        prepared = cache.get(value.id)
        if (
            prepared is None
            or prepared[0] is not value
            or prepared[1] != view.grid
            or prepared[2] != font_key
        ):
            path = local_path(value)
            matrix = transform(value)
            bounds = matrix.mapRect(path.boundingRect())
            anchor = matrix.map(path.boundingRect().topLeft())
            text = (value.name + " · " if value.name else "") + dimensions(value, view.grid)
            label = painter.fontMetrics().boundingRect(text).adjusted(-5, -3, 5, 3)
            pen = QPen(QColor(value.color), 2)
            pen.setCosmetic(True)
            fill = QColor(value.color)
            fill.setAlphaF(value.opacity)
            prepared = (
                value,
                view.grid,
                font_key,
                path,
                matrix,
                bounds,
                anchor,
                text,
                label,
                pen,
                fill,
            )
            cache[value.id] = prepared
        _, _, _, path, matrix, bounds, anchor, text, label, pen, fill = prepared
        if not bounds.intersects(exposed):
            continue
        painter.save()
        painter.setWorldTransform(matrix, True)
        painter.setPen(pen)
        painter.setBrush(fill)
        painter.drawPath(path)
        painter.restore()
        point = view.viewportTransform().map(anchor)
        painter.save()
        painter.resetTransform()
        rect = label.translated(point.toPoint() - label.bottomLeft())
        painter.fillRect(rect, QColor("#202020"))
        painter.setPen(QColor("#eeeeee"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()
    if len(cache) > len(view.vector_shapes) + 2:
        keep = {v.id for v in shapes}
        view._vector_render_cache = {key: v for key, v in cache.items() if key in keep}
    if view.role != "player":
        for portal in view.vector_portals:
            if tools and tools.preview and mode_is_portal(tools.gesture):
                if tools.preview.id == portal.id:
                    portal = tools.preview
            painter.save()
            center = painter.worldTransform().map(QPointF(portal.x, portal.y))
            painter.resetTransform()
            painter.setPen(QPen(QColor("#b6a4ff"), 2))
            painter.setBrush(QColor("#202020"))
            painter.drawEllipse(center, 12, 12)
            painter.drawText(
                QRectF(center.x() - 8, center.y() - 10, 16, 20), Qt.AlignmentFlag.AlignCenter, "↗"
            )
            if not portal.hide_label:
                painter.drawText(
                    center + QPointF(17, 4),
                    getattr(view, "portal_labels", {}).get(portal.id, portal.label or "Портал"),
                )
            painter.restore()
    if tools:
        tools.paint_handles(painter)
    painter.restore()


class VectorTools(QWidget):
    committed = Signal(object)
    token_transformed = Signal(object, object)
    removed = Signal(str)
    portal_requested = Signal(float, float)
    portal_opened = Signal(str)
    portal_edited = Signal(str)
    inspector_requested = Signal(object)

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        view.vector_tools = self
        self.points = []
        self.selected = None
        self.transform_selection = None
        self.preview = None
        self.gesture = None
        self.preview_cursor = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.notice = QLabel("Фигуры видны игрокам поверх тумана. Escape — отмена")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.inspector = QWidget()
        self.destroyed.connect(self.inspector.deleteLater)
        form = QFormLayout(self.inspector)
        self.name = QLineEdit()
        self.color = QPushButton("#73d6b2")
        self.color.clicked.connect(self.choose_color)
        self.color.setToolTip("Выбрать цвет фигуры")
        self.opacity = QDoubleSpinBox()
        self.opacity.setRange(0, 100)
        self.opacity.setSuffix("%")
        self.opacity.setSingleStep(5)
        self.rotation = QDoubleSpinBox()
        self.rotation.setRange(-360, 360)
        for label, control in (
            ("Название", self.name),
            ("Цвет", self.color),
            ("Непрозрачность", self.opacity),
            ("Поворот", self.rotation),
        ):
            form.addRow(label, control)
        apply = QPushButton("Применить свойства")
        apply.clicked.connect(self.apply_properties)
        form.addRow(apply)
        delete = QPushButton("Удалить фигуру")
        delete.clicked.connect(self.delete)
        form.addRow(delete)
        view.viewport().installEventFilter(self)
        view.installEventFilter(self)
        view.viewport().setMouseTracking(True)
        view.model_changed.connect(self._cancel_stale_transform)
        view.scene().selectionChanged.connect(self._token_selection_changed)
        view.tool_state.vectors = self
        view.tool_state.prioritize()

    def choose_color(self):
        value = QColorDialog.getColor(QColor(self.color.text()), self.inspector, "Цвет фигуры")
        if value.isValid():
            self.color.setText(value.name())
            pixmap = QPixmap(16, 16)
            pixmap.fill(value)
            self.color.setIcon(QIcon(pixmap))

    @property
    def mode(self):
        return self.view.tool_state.vector_mode

    @property
    def enabled(self):
        return self.view.tool_state.vectors_enabled

    def set_mode(self, mode):
        self.view.tool_state.activate(mode)

    def cancel(self):
        if getattr(self, "view", None) is None or not isValid(self.view):
            return
        if self.gesture and self.gesture[0] in TOKEN_TRANSFORMS:
            item = self.gesture[1].item
            if isValid(item):
                item.set_transform_preview(None)
        self.points.clear()
        self.preview = None
        self.gesture = None
        self.view.viewport().update()

    def value(self):
        return next((v for v in self.view.vector_shapes if v.id == self.selected), None)

    def selected_transform_item(self):
        item = self.transform_selection
        return item if item is not None and isValid(item) and item.can_transform else None

    def _cancel_stale_transform(self):
        if self.gesture and self.gesture[0] in TOKEN_TRANSFORMS:
            resize = self.gesture[1]
            if resize.item is not self.selected_transform_item() or not resize.is_current():
                self.cancel()

    def _token_selection_changed(self):
        if not isValid(self.view):
            return
        selected = self.view.scene().selectedItems()
        self.transform_selection = (
            selected[0] if len(selected) == 1 and isinstance(selected[0], TokenItem) else None
        )
        self._cancel_stale_transform()
        if self.selected and self.selected_transform_item() is not None:
            self.cancel()
            self.select(None)
        self.view.viewport().update()

    def select(self, value):
        self.selected = value.id if value else None
        self.inspected = value
        if value:
            item = self.selected_transform_item()
            if item is not None:
                item.setSelected(False)
            self.name.setText(value.name)
            self.color.setText(value.color)
            self.opacity.setValue(value.opacity * 100)
            self.rotation.setValue(value.rotation)
            self.inspector_requested.emit(self.inspector)
        self.view.viewport().update()

    def apply_properties(self):
        value = self.value()
        if value is None:
            return
        if value != self.inspected:
            self.notice.setText("Фигура изменена другим представлением. Выберите её заново.")
            return
        try:
            candidate = replace(
                value,
                name=self.name.text(),
                color=self.color.text(),
                opacity=self.opacity.value() / 100,
                rotation=self.rotation.value(),
            )
            self.committed.emit(candidate)
            if self.value() == candidate:
                self.inspected = candidate
        except ValueError as error:
            self.notice.setText(str(error))

    def delete(self):
        if self.selected:
            self.removed.emit(self.selected)
            self.selected = None
            self.cancel()

    def finish(self):
        try:
            x = sum(p[0] for p in self.points) / len(self.points)
            y = sum(p[1] for p in self.points) / len(self.points)
            value = MapShape(self.mode, tuple((a - x, b - y) for a, b in self.points), x=x, y=y)
            self.committed.emit(value)
            self.cancel()
            self.select(value)
        except ValueError as error:
            self.notice.setText(str(error))

    def handles(self, value):
        rect = local_path(value).boundingRect()
        mapping = transform(value)
        points = (
            list(value.points)
            if self.mode == "vertices" and value.kind not in {"circle", "cone", "rectangle"}
            else [(rect.right(), rect.bottom())]
        )
        mapped = [mapping.map(QPointF(*p)) for p in points]
        return mapped + [rotation_handle(self.view, mapping, rect)]

    def handle_distance_squared(self, a, b):
        delta = self.view.viewportTransform().map(a) - self.view.viewportTransform().map(b)
        return delta.x() ** 2 + delta.y() ** 2

    def near(self, a, b, radius=10):
        return self.handle_distance_squared(a, b) <= radius**2

    def _object_handle(self, item, point):
        matrix, rect = item.sceneTransform(), item.boundingRect()
        if self.near(point, rotation_handle(self.view, matrix, rect)):
            return "rotate_token", None
        corner = min(
            resize_corners(rect), key=lambda p: self.handle_distance_squared(matrix.map(p), point),
        )
        return ("resize_token", corner) if self.near(point, matrix.map(corner)) else None

    def paint_handles(self, painter):
        value = self.preview or self.value()
        if isinstance(value, MapShape) and self.selected == value.id:
            paint_edit_handles(painter, self.handles(value))
        if (item := self.selected_transform_item()) is not None:
            matrix, rect = item.sceneTransform(), item.boundingRect()
            corners = tuple(matrix.map(p) for p in resize_corners(rect))
            rotation = rotation_handle(self.view, matrix, rect)
            paint_edit_handles(painter, (*corners, rotation), frame=corners)
        if self.points:
            path = QPainterPath(QPointF(*self.points[0]))
            for p in self.points[1:]:
                path.lineTo(QPointF(*p))
            if self.preview_cursor is not None:
                cursor = self.preview_cursor
                snapped = len(self.points) >= 3 and self.near(cursor, QPointF(*self.points[0]))
                path.lineTo(QPointF(*self.points[0]) if snapped else cursor)
            painter.setPen(QPen(QColor("#eeeeee"), 0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            for i, p in enumerate(self.points):
                painter.save()
                point = painter.worldTransform().map(QPointF(*p))
                painter.resetTransform()
                painter.setBrush(
                    QColor(
                        "#73d6b2"
                        if i == 0
                        and len(self.points) >= 3
                        and self.preview_cursor is not None
                        and self.near(self.preview_cursor, QPointF(*p))
                        else "#303030"
                    )
                )
                painter.drawEllipse(point, 5, 5)
                painter.restore()

    def eventFilter(self, watched, event):
        if getattr(self, "view", None) is None or not isValid(self.view):
            return False
        if self.view.role != "viewer" or not self.enabled:
            return False
        kind = event.type()
        if (
            kind in {QEvent.Type.KeyPress, QEvent.Type.KeyRelease}
            and self.gesture and self.gesture[0] in TOKEN_TRANSFORMS
            and (modifier := TRANSFORM_KEYS.get(event.key())) is not None
        ):
            modifiers = event.modifiers()
            if kind == QEvent.Type.KeyPress:
                modifiers |= modifier
            else:
                modifiers &= ~modifier
            self.update_gesture(self.preview_cursor, modifiers)
            return True
        if kind == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.cancel()
                return True
            if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and self.points:
                self.finish()
                return True
            if event.key() == Qt.Key.Key_Delete and self.selected:
                self.delete()
                return True
        if watched is not self.view.viewport():
            return False
        if kind not in {
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
        }:
            return False
        point = self.view.viewportTransform().inverted()[0].map(event.position())
        self.preview_cursor = point
        if kind == QEvent.Type.MouseMove:
            if self.gesture:
                self.update_gesture(point, event.modifiers())
            if not self.gesture and self.mode in {"select", "vertices"}:
                value = self.value()
                item = self.selected_transform_item()
                hover = (
                    item is not None and self._object_handle(item, point) is not None
                ) or (value and any(self.near(point, p) for p in self.handles(value)))
                self.view.viewport().setCursor(
                    Qt.CursorShape.CrossCursor if hover else Qt.CursorShape.ArrowCursor
                )
            self.view.viewport().update()
            return bool(self.gesture or self.points or self.mode not in {"select", "vertices"})
        if event.button() == Qt.MouseButton.RightButton and kind == QEvent.Type.MouseButtonPress:
            portal = next(
                (p for p in self.view.vector_portals if self.near(point, QPointF(p.x, p.y), 16)),
                None,
            )
            if portal:
                menu = QMenu(self)
                edit = menu.addAction("Перепривязать / изменить подпись")
                delete = menu.addAction("Удалить портал")
                chosen = menu.exec(event.globalPosition().toPoint())
                if chosen == edit:
                    self.portal_edited.emit(portal.id)
                elif chosen == delete:
                    self.removed.emit(portal.id)
                return True
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if kind == QEvent.Type.MouseButtonRelease and self.gesture:
            if self.gesture[0] in TOKEN_TRANSFORMS:
                edit = self.gesture[1]
                self.update_gesture(point, event.modifiers())
                candidate = edit.item.transform_preview if self.gesture else None
                self.cancel()
                if candidate is not None and candidate != edit.token:
                    self.token_transformed.emit(edit.token, candidate)
                return True
            value = self.preview
            previous = self.gesture[1]
            current = (
                next((v for v in self.view.vector_portals if v.id == previous.id), None)
                if previous and mode_is_portal(self.gesture)
                else self.value()
            )
            if previous and current != previous:
                self.notice.setText("Фигура изменена другим представлением. Повторите жест.")
                self.cancel()
                return True
            self.cancel()
            if value:
                self.committed.emit(value)
                self.select(value)
            return True
        if kind not in {QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick}:
            return False
        if self.mode == "portal":
            self.portal_requested.emit(point.x(), point.y())
            return True
        if self.mode in {"select", "vertices"}:
            item = self.selected_transform_item()
            if item is not None and kind == QEvent.Type.MouseButtonPress:
                handle = self._object_handle(item, point)
                if handle is not None:
                    self.view.setFocus()
                    edit = TokenTransform(
                        item, item.token, (item.presentation.cells_w, item.presentation.cells_h),
                        item.cell_size, item.boundingRect(), item.sceneTransform(),
                    )
                    self.gesture = (handle[0], edit, point, handle[1])
                    return True
            for portal in reversed(self.view.vector_portals):
                if self.near(point, QPointF(portal.x, portal.y), 16):
                    if item is not None:
                        item.setSelected(False)
                    self.selected = portal.id
                    if kind == QEvent.Type.MouseButtonDblClick:
                        self.portal_opened.emit(portal.id)
                    else:
                        self.gesture = ("portal", portal, point, 0)
                    return True
            value = self.value()
            if value:
                handles = self.handles(value)
                for index, handle in enumerate(handles):
                    if self.near(point, handle):
                        self.gesture = (
                            "rotate"
                            if index == len(handles) - 1
                            else "vertex"
                            if self.mode == "vertices"
                            and value.kind not in {"circle", "cone", "rectangle"}
                            else "resize",
                            value,
                            point,
                            index,
                        )
                        return True
            for value in reversed(self.view.vector_shapes):
                if transform(value).map(local_path(value)).contains(point):
                    self.select(value)
                    self.gesture = ("move", value, point, 0)
                    return True
            self.select(None)
            return False
        if self.mode in {"circle", "cone", "rectangle"}:
            self.gesture = ("create", None, point, 0)
            return True
        if (
            self.mode == "polygon"
            and len(self.points) >= 3
            and self.near(point, QPointF(*self.points[0]))
        ):
            self.finish()
            return True
        if len(self.points) >= 512:
            self.notice.setText("Не более512 вершин. Отмените жест или замкните контур.")
            return True
        self.points.append((point.x(), point.y()))
        expected = {"triangle": 3, "quadrilateral": 4}.get(self.mode)
        if expected and len(self.points) == expected:
            self.finish()
        self.view.viewport().update()
        return True

    def update_gesture(self, point, modifiers):
        mode, value, start, index = self.gesture
        try:
            if mode in TOKEN_TRANSFORMS:
                if not value.is_current():
                    self.cancel()
                    return
                if mode == "resize_token":
                    candidate = value.resized(index, point - start, modifiers)
                else:
                    candidate = value.token
                    if point != start:
                        center = QPointF(candidate.x, candidate.y)
                        angle = rotation_for_drag(
                            candidate.rotation, center, start, point, modifiers,
                        )
                        candidate = replace(candidate, rotation=angle)
                value.item.set_transform_preview(candidate)
                self.view.viewport().update()
                return
            if mode == "create":
                dx, dy = point.x() - start.x(), point.y() - start.y()
                length = math.hypot(dx, dy)
                if self.mode == "rectangle":
                    value = MapShape(
                        "rectangle",
                        (
                            (-dx / 2, -dy / 2),
                            (dx / 2, -dy / 2),
                            (dx / 2, dy / 2),
                            (-dx / 2, dy / 2),
                        ),
                        x=start.x() + dx / 2,
                        y=start.y() + dy / 2,
                    )
                else:
                    value = MapShape(
                        self.mode,
                        ((length, 0),),
                        x=start.x(),
                        y=start.y(),
                        rotation=math.degrees(math.atan2(dy, dx)) if self.mode == "cone" else 0,
                    )
            elif mode in {"move", "portal"}:
                delta = point - start
                value = replace(value, x=value.x + delta.x(), y=value.y + delta.y())
            elif mode == "rotate":
                angle = rotation_for_drag(
                    value.rotation, QPointF(value.x, value.y), start, point, modifiers,
                )
                value = replace(value, rotation=angle)
            elif mode == "vertex":
                local = transform(value).inverted()[0].map(point)
                points = list(value.points)
                points[index] = (local.x(), local.y())
                value = replace(value, points=tuple(points))
            else:
                rect = local_path(value).boundingRect()
                local = transform(value).inverted()[0].map(point)
                center, sx, sy = resize_factors(
                    rect, rect.bottomRight(), local, modifiers,
                    uniform=value.kind in {"circle", "cone"},
                )
                if value.kind in {"circle", "cone"}:
                    new_scale = max(0.0001, min(1e5, value.scale * max(sx, sy)))
                    anchor_world = transform(value).map(center)
                    rotated = (
                        QTransform().rotate(value.rotation).scale(new_scale, new_scale).map(center)
                    )
                    value = replace(
                        value,
                        scale=new_scale,
                        x=anchor_world.x() - rotated.x(),
                        y=anchor_world.y() - rotated.y(),
                    )
                else:
                    value = replace(
                        value,
                        points=tuple(
                            (center.x() + (x - center.x()) * sx, center.y() + (y - center.y()) * sy)
                            for x, y in value.points
                        ),
                    )
            self.preview = value
            self.view.viewport().update()
        except ValueError as error:
            if mode in TOKEN_TRANSFORMS:
                return  # Keep the last representable preview when a handle crosses its anchor.
            self.preview = None
            self.notice.setText(str(error))
