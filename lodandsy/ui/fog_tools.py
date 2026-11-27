"""GM-only gesture buffer. Only a completed gesture reaches MapsService."""

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QPainterPath
from PySide6.QtWidgets import (
    QBoxLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from lodandsy.application.fog_geometry import (
    MAX_BRUSH_POINTS,
    brush_stamp,
    brush_stroke_path,
    polygon_path,
    region_path,
)
from lodandsy.domain.map_fog import MAX_GESTURE_POINTS

PREVIEW_SEGMENT_POINTS = 24


class FogTools(QWidget):
    edited = Signal(object, bool)
    deleted = Signal(str)

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.points = []
        self._brush_segments = []
        self._brush_tail = QPainterPath()
        self._brush_start = 0
        self._cursor = None
        self.selected = None
        self.snap_radius = 10.0
        view.viewport().setMouseTracking(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
        row = self.parameter_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.brush_group = QWidget()
        brush = QHBoxLayout(self.brush_group)
        brush.setContentsMargins(0, 0, 0, 0)
        brush.addWidget(QLabel("Размер"))
        self.size = QSpinBox()
        self.size.setRange(1, 100000)
        self.size.setValue(128)
        self.size.setSuffix(" px мира")
        self.size.setAccessibleName("Размер кисти тумана")
        self.size.setMaximumWidth(132)
        self.size.valueChanged.connect(self._brush_size_changed)
        brush.addWidget(self.size)
        row.addWidget(self.brush_group, 0, Qt.AlignmentFlag.AlignLeft)
        opacity_group = QWidget()
        opacity_row = QHBoxLayout(opacity_group)
        opacity_row.setContentsMargins(0, 0, 0, 0)
        opacity_row.addWidget(QLabel("Ведущий"))
        self.opacity = QSpinBox()
        self.opacity.setRange(0, 100)
        self.opacity.setValue(50)
        self.opacity.setSuffix("%")
        self.opacity.valueChanged.connect(self._opacity)
        self.opacity.setAccessibleName("Непрозрачность тумана для ведущего")
        self.opacity.setMaximumWidth(76)
        opacity_row.addWidget(self.opacity)
        row.addWidget(opacity_group, 0, Qt.AlignmentFlag.AlignLeft)
        row.addStretch(1)
        layout.addLayout(row)
        self.notice = QLabel(
            "Enter — завершить полигон · Escape — отмена · "
            "Space — панорама · Delete — удалить область"
        )
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        view.installEventFilter(self)
        view.viewport().installEventFilter(self)
        view.tool_state.fog = self
        view.tool_state.prioritize()
        self.hide()

    def resizeEvent(self, event):
        self.parameter_row.setDirection(
            QBoxLayout.Direction.TopToBottom
            if event.size().width() < 360
            else QBoxLayout.Direction.LeftToRight
        )
        super().resizeEvent(event)

    def _opacity(self, value):
        self.view.fog_opacity = value / 100
        self.view.viewport().update()

    @property
    def mode(self):
        from lodandsy.ui.map_tools import FOG

        return FOG.get(self.view.tool_state.active, "select")

    def set_mode(self, mode):
        self.view.tool_state.activate("fog_" + mode)

    def brush_outline(self):
        if self._cursor is None or self.mode not in {"hide", "erase"}:
            return None
        if self.view._background is None or not QRectF(self.view.viewport().rect()).contains(
            self._cursor
        ):
            return None
        point = self.view.viewportTransform().inverted()[0].map(self._cursor)
        if QRectF(0, 0, self.view.map_width, self.view.map_height).contains(point):
            return brush_stamp(point, self.size.value())
        return None

    def _brush_size_changed(self):
        if self.points and self.mode in {"hide", "erase"}:
            self._clear_brush_preview()
            self._preview()
        self.view.viewport().update()

    def _snaps(self, point):
        if len(self.points) < 3:
            return False
        first = self.view.viewportTransform().map(QPointF(*self.points[0]))
        delta = self.view.viewportTransform().map(point) - first
        return delta.x() ** 2 + delta.y() ** 2 <= self.snap_radius**2

    def cancel(self):
        if getattr(self, "view", None) is None or not isValid(self.view):
            return
        self.points.clear()
        self._clear_brush_preview()
        self.view._fog_vertices = ()
        self.view._fog_snap = False
        self.selected = None
        self.view._fog_preview = QPainterPath()
        self.view._fog_selection = QPainterPath()
        self.view.viewport().update()

    def _clear_brush_preview(self):
        self._brush_segments.clear()
        self._brush_tail = QPainterPath()
        self._brush_start = 0

    def brush_preview(self, exposed):
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.WindingFill)
        for bounds, segment in self._brush_segments:
            if exposed.intersects(bounds):
                path.addPath(segment)
        if exposed.intersects(self._brush_tail.controlPointRect()):
            path.addPath(self._brush_tail)
        return path

    def _preview(self, cursor=None):
        try:
            if self.mode == "polygon":
                path = QPainterPath()
                if self.points:
                    path.moveTo(QPointF(*self.points[0]))
                    for point in self.points[1:]:
                        path.lineTo(QPointF(*point))
                    snapped = cursor is not None and self._snaps(cursor)
                    self.view._fog_snap = snapped
                    self.view._fog_vertices = tuple(self.points)
                    if cursor is not None:
                        path.lineTo(QPointF(*self.points[0]) if snapped else cursor)
            else:
                previous = self._brush_tail.controlPointRect()
                while len(self.points) - self._brush_start > PREVIEW_SEGMENT_POINTS:
                    end = self._brush_start + PREVIEW_SEGMENT_POINTS
                    segment = brush_stroke_path(
                        self.points[self._brush_start:end + 1], self.size.value()
                    )
                    self._brush_segments.append((segment.controlPointRect(), segment))
                    previous = previous.united(segment.controlPointRect())
                    self._brush_start = end
                self._brush_tail = brush_stroke_path(
                    self.points[self._brush_start:], self.size.value()
                )
                self._update_world(previous.united(self._brush_tail.controlPointRect()))
                return
            self.view._fog_preview = path
            self.view.viewport().update()
        except ValueError as error:
            self.notice.setText(str(error))
            self.cancel()

    def _append(self, point):
        if self.mode in {"hide", "erase"}:
            if len(self.points) == MAX_BRUSH_POINTS:
                self.notice.setText("Предел длины жеста. Отпустите кнопку, чтобы применить мазок.")
                return False
            self.points.append((point.x(), point.y()))
            return True
        if len(self.points) >= MAX_GESTURE_POINTS:
            self.notice.setText(
                "Жест превышает512 точек. Используйте несколько более коротких жестов."
            )
            self.cancel()
            return False
        self.points.append((point.x(), point.y()))
        return True

    def finish(self):
        if not self.points:
            return
        try:
            path = (
                polygon_path(tuple(self.points))
                if self.mode == "polygon"
                else brush_stroke_path(self.points, self.size.value()).simplified()
            )
            self.edited.emit(path, self.mode == "erase")
        except ValueError as error:
            self.notice.setText(str(error))
        self.cancel()

    def _update_world(self, bounds):
        pixel = self.view.viewportTransform().mapRect(bounds).toAlignedRect()
        self.view.viewport().update(pixel.adjusted(-3, -3, 3, 3))

    def eventFilter(self, watched, event):
        if getattr(self, "view", None) is None or not isValid(self.view):
            return False
        kind = event.type()
        if watched is self.view.viewport():
            old_outline = self.brush_outline()
            if kind in {
                QEvent.Type.Enter, QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonRelease, QEvent.Type.Wheel,
            }:
                self._cursor = event.position()
            elif kind == QEvent.Type.Leave:
                self._cursor = None
            if self.mode in {"hide", "erase"} and kind in {
                QEvent.Type.Enter, QEvent.Type.Leave, QEvent.Type.MouseMove,
            }:
                for outline in (old_outline, self.brush_outline()):
                    if outline is not None:
                        self._update_world(outline.controlPointRect())
        if not self.view.tool_state.active.startswith("fog_"):
            return False
        if kind == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.cancel()
                return True
            if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and self.mode == "polygon":
                self.finish()
                return True
            if event.key() == Qt.Key.Key_Delete and self.selected:
                self.deleted.emit(self.selected)
                self.cancel()
                return True
        if watched is not self.view.viewport() or self.view._background is None:
            return False
        if kind not in {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
        }:
            return False
        if kind == QEvent.Type.MouseMove:
            point = self.view.viewportTransform().inverted()[0].map(event.position())
            if self.points and self.mode in {"hide", "erase"}:
                previous = QPointF(*self.points[-1])
                if (point - previous).manhattanLength() >= max(1, self.size.value() / 8):
                    if self._append(point):
                        self._preview()
            elif self.mode == "polygon" and self.points:
                self._preview(point)
            return True
        if event.button() != Qt.MouseButton.LeftButton:
            return True
        point = self.view.viewportTransform().inverted()[0].map(event.position())
        if kind == QEvent.Type.MouseButtonPress:
            self.view.setFocus()
            if self.mode == "select":
                self.selected = next(
                    (
                        r.id
                        for r in reversed(self.view._fog_state.regions)
                        if region_path(r).contains(point)
                    ),
                    None,
                )
                region = next(
                    (r for r in self.view._fog_state.regions if r.id == self.selected), None
                )
                self.view._fog_selection = region_path(region) if region else QPainterPath()
                self.view.viewport().update()
            elif self.mode == "polygon":
                if self._snaps(point):
                    self.finish()
                elif self._append(point):
                    self._preview()
            else:
                self.cancel()
                self._append(point)
                self._preview()
        elif (
            kind == QEvent.Type.MouseButtonRelease
            and self.mode in {"hide", "erase"}
            and self.points
        ):
            self._append(point)
            self.finish()
        return True
