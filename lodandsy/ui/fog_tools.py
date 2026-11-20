"""GM-only gesture buffer. Only a completed gesture reaches MapsService."""

from PySide6.QtCore import QEvent, QPointF, Qt, Signal
from PySide6.QtGui import QActionGroup, QPainterPath
from PySide6.QtWidgets import QLabel, QSpinBox, QToolBar, QVBoxLayout, QWidget

from lodandsy.application.fog_geometry import polygon_path, region_path, stroke_path
from lodandsy.domain.map_fog import MAX_GESTURE_POINTS


class FogTools(QWidget):
    edited = Signal(object, bool)
    deleted = Signal(str)

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.mode = "hide"
        self.points = []
        self.selected = None
        self.panning = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QToolBar()
        group = QActionGroup(self)
        for label, mode in [
            ("Кисть", "hide"),
            ("Ластик", "erase"),
            ("Полигон", "polygon"),
            ("Выбор", "select"),
        ]:
            action = bar.addAction(label)
            action.setCheckable(True)
            action.setChecked(mode == self.mode)
            group.addAction(action)
            action.triggered.connect(lambda checked=False, value=mode: self.set_mode(value))
        bar.addSeparator()
        bar.addWidget(QLabel("Размер:"))
        self.size = QSpinBox()
        self.size.setRange(1, 100000)
        self.size.setValue(128)
        self.size.setSuffix(" px мира")
        self.size.setAccessibleName("Размер кисти тумана")
        bar.addWidget(self.size)
        bar.addSeparator()
        bar.addWidget(QLabel("Видимость GM:"))
        self.opacity = QSpinBox()
        self.opacity.setRange(0, 100)
        self.opacity.setValue(50)
        self.opacity.setSuffix("%")
        self.opacity.valueChanged.connect(self._opacity)
        bar.addWidget(self.opacity)
        layout.addWidget(bar)
        self.notice = QLabel(
            "Enter — завершить полигон · Escape — отмена · "
            "Space — панорама · Delete — удалить область"
        )
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        view.installEventFilter(self)
        view.viewport().installEventFilter(self)
        self.hide()

    def _opacity(self, value):
        self.view.fog_opacity = value / 100
        self.view.viewport().update()

    def set_mode(self, mode):
        self.cancel()
        self.mode = mode

    def setVisible(self, visible):
        self.cancel()
        super().setVisible(visible)

    def cancel(self):
        self.points.clear()
        self.selected = None
        self.view._fog_preview = QPainterPath()
        self.view._fog_selection = QPainterPath()
        self.view.viewport().update()

    def _preview(self, cursor=None):
        try:
            if self.mode == "polygon":
                path = QPainterPath()
                if self.points:
                    path.moveTo(QPointF(*self.points[0]))
                    for point in self.points[1:]:
                        path.lineTo(QPointF(*point))
                    if cursor:
                        path.lineTo(cursor)
            else:
                path = stroke_path(self.points, self.size.value())
            self.view._fog_preview = path
            self.view.viewport().update()
        except ValueError as error:
            self.notice.setText(str(error))
            self.cancel()

    def _append(self, point):
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
                else stroke_path(self.points, self.size.value())
            )
            self.edited.emit(path, self.mode == "erase")
        except ValueError as error:
            self.notice.setText(str(error))
        self.cancel()

    def eventFilter(self, watched, event):
        if not self.isVisible():
            return False
        kind = event.type()
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
            if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
                self.cancel()
                self.panning = True
                return False
        if kind == QEvent.Type.KeyRelease and event.key() == Qt.Key.Key_Space:
            self.panning = False
            return False
        if self.panning or watched is not self.view.viewport() or self.view._background is None:
            return False
        if kind not in {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
        }:
            return False
        if kind == QEvent.Type.MouseMove:
            point = self.view.mapToScene(event.position().toPoint())
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
        point = self.view.mapToScene(event.position().toPoint())
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
                first = self.view.mapFromScene(QPointF(*self.points[0])) if self.points else None
                if (
                    len(self.points) >= 3
                    and (event.position().toPoint() - first).manhattanLength() <= 8
                ):
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
            if self._append(point):
                self.finish()
        return True
