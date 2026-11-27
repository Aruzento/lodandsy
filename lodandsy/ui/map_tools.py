"""One per-view tool state and native projections. No world data lives here."""

from PySide6.QtCore import QEvent, QObject, QPoint, QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsView,
    QLabel,
    QMenu,
    QProxyStyle,
    QSizePolicy,
    QStyle,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from lodandsy.ui.icons import icon
from lodandsy.ui.map_settings_dialogs import measurement_picker
from lodandsy.ui.theme import MAP_TOOLBAR_STYLE, MAP_TOOLBAR_VERTICAL_STYLE

SHAPES = {
    "circle": "Круг",
    "rectangle": "Прямоугольник",
    "triangle": "Треугольник",
    "quadrilateral": "Четырёхугольник",
    "cone": "Конус",
    "polygon": "Многоугольник",
}
FOG = {"fog_hide": "hide", "fog_erase": "erase", "fog_polygon": "polygon", "fog_select": "select"}
LABELS = {
    "select": "Выбор",
    "pan": "Рука",
    "token": "Добавить токен",
    "vertices": "Редактировать вершины",
    "portal": "Портал",
    "fog_hide": "Кисть тумана",
    "fog_erase": "Ластик тумана",
    "fog_polygon": "Многоугольник тумана",
    "fog_select": "Выбрать область тумана",
    **SHAPES,
}
HINTS = {
    "select": "Выбор · V. Двойной щелчок по порталу — перейти на карту.",
    "pan": "Рука · H. Перетащите карту. Space — временная панорама.",
    "token": "Щёлкните по карте, чтобы выбрать и добавить токен.",
    "vertices": "Выберите фигуру и перетащите вершину. Escape — отмена.",
    "portal": "Щёлкните по карте и выберите назначение портала.",
    "figure": "Фигуры видны игрокам поверх тумана. Enter — завершить, Escape — отмена.",
}


class MapToolState(QObject):
    changed = Signal(str)

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self._active = "select"
        self.last_shape = "circle"
        self.last_selection = "select"
        self._space_previous = None
        self.fog = None
        self.vectors = None
        self.prioritize()

    def prioritize(self):
        for surface in (self.view, self.view.viewport()):
            surface.removeEventFilter(self)
            surface.installEventFilter(self)

    @property
    def active(self):
        return self._active

    @property
    def vector_mode(self):
        return (
            self.active
            if self.active in SHAPES or self.active in {"vertices", "portal"}
            else "select"
        )

    @property
    def vectors_enabled(self):
        return self.active in SHAPES or self.active in {"select", "vertices", "portal"}

    def cancel(self):
        if getattr(self, "view", None) is None or not isValid(self.view):
            return
        if self.fog:
            self.fog.cancel()
        if self.vectors:
            self.vectors.cancel()
        self.view.cancel_token_drag()

    def activate(self, tool, *, temporary=False):
        if getattr(self, "view", None) is None or not isValid(self.view):
            return
        if tool not in LABELS:
            raise ValueError("Неизвестный инструмент карты")
        if not temporary:
            self._space_previous = None
        self.cancel()
        self._active = tool
        if tool in {"select", "vertices"}:
            self.last_selection = tool
        if tool in SHAPES:
            self.last_shape = tool
        self.view.setDragMode(
            QGraphicsView.DragMode.ScrollHandDrag
            if tool == "pan"
            else QGraphicsView.DragMode.RubberBandDrag
            if tool in {"select"}
            else QGraphicsView.DragMode.NoDrag
        )
        for item in self.view._tokens:
            enabled = self.view.token_interaction_enabled
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                enabled and self.view._background is not None,
            )
            item.setAcceptedMouseButtons(
                Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
                if enabled
                else Qt.MouseButton.NoButton
            )
        self.changed.emit(tool)
        self.view.viewport().setCursor(
            Qt.CursorShape.OpenHandCursor
            if tool == "pan"
            else Qt.CursorShape.ArrowCursor
            if tool in {"select", "fog_select"}
            else Qt.CursorShape.CrossCursor
        )
        self.view.viewport().update()

    def restore_space(self):
        previous, self._space_previous = self._space_previous, None
        if previous is not None:
            self.activate(previous)

    def eventFilter(self, watched, event):
        if getattr(self, "view", None) is None or not isValid(self.view):
            return False
        kind = event.type()
        if kind == QEvent.Type.FocusOut:
            self.cancel()
            self.restore_space()
            return False
        if kind == QEvent.Type.KeyRelease and event.key() == Qt.Key.Key_Space:
            if not event.isAutoRepeat():
                self.restore_space()
            return True
        if kind == QEvent.Type.KeyPress and not (
            event.modifiers()
            & (
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.AltModifier
                | Qt.KeyboardModifier.MetaModifier
            )
        ):
            key = event.key()
            if key == Qt.Key.Key_Space:
                if not event.isAutoRepeat() and self._space_previous is None:
                    self._space_previous = self.active
                    self.activate("pan", temporary=True)
                return True
            if key == Qt.Key.Key_Escape:
                self.cancel()
                return True
            shortcuts = {
                int(Qt.Key.Key_V): "select",
                int(Qt.Key.Key_H): "pan",
                int(Qt.Key.Key_B): "fog_hide",
                int(Qt.Key.Key_E): "fog_erase",
                int(Qt.Key.Key_M): self.last_shape,
            }
            key = event.nativeVirtualKey() if event.nativeVirtualKey() in shortcuts else int(key)
            if key in shortcuts:
                if not event.isAutoRepeat():
                    self.activate(shortcuts[key])
                return True
        if (
            watched is self.view.viewport()
            and kind == QEvent.Type.MouseButtonPress
            and self.active == "token"
            and event.button() == Qt.MouseButton.LeftButton
        ):
            point = self.view.mapToScene(event.position().toPoint())
            if (
                self.view._background is not None
                and 0 <= point.x() <= self.view.map_width
                and 0 <= point.y() <= self.view.map_height
            ):
                self.view.setFocus()
                self.view.token_add_requested.emit(point.x(), point.y())
            return True
        return False


def tool_icon(name):
    return icon(name, 18, stroke_width=1.15)


class ToolMenu(QMenu):
    """Native flyout with a logical-pixel gutter and screen-aware placement."""

    def showEvent(self, event):
        super().showEvent(event)
        button = self.parentWidget()
        bounds = button.screen().availableGeometry()
        anchor = button.mapToGlobal(QPoint(button.width() + 10, 0))
        if anchor.x() + self.width() > bounds.right() + 1:
            anchor.setX(button.mapToGlobal(QPoint(-10 - self.width(), 0)).x())
        anchor.setX(max(bounds.left(), min(anchor.x(), bounds.right() + 1 - self.width())))
        anchor.setY(max(bounds.top(), min(anchor.y(), bounds.bottom() + 1 - self.height())))
        self.move(anchor)


class MapToolbarStyle(QProxyStyle):
    def pixelMetric(self, metric, option=None, widget=None):
        if metric == QStyle.PixelMetric.PM_ToolBarExtensionExtent:
            return 36
        return super().pixelMetric(metric, option, widget)


def style_toolbar(bar, vertical=False):
    style = MapToolbarStyle("Fusion")
    style.setParent(bar)
    bar.setStyle(style)
    bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    bar.setIconSize(QSize(18, 18))
    bar.setStyleSheet(MAP_TOOLBAR_STYLE + (MAP_TOOLBAR_VERTICAL_STYLE if vertical else ""))
    if vertical:
        bar.setOrientation(Qt.Orientation.Vertical)
        bar.setFixedWidth(44)
        bar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Ignored)
    else:
        bar.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)


class MapToolbars(QObject):
    grid_settings_requested = Signal()
    grid_toggled = Signal(bool)
    editor_requested = Signal()
    presentation_requested = Signal()

    def __init__(self, view, fog, vectors, parent):
        super().__init__(parent)
        self.view, self.state, self.fog, self.vectors = view, view.tool_state, fog, vectors
        self.sidebar = QToolBar(parent)
        style_toolbar(self.sidebar, True)
        self.general = QToolBar(parent)
        style_toolbar(self.general)
        self.actions = {}
        self.shape_actions = {}
        group = QActionGroup(self)
        shortcuts = {"select": "V", "pan": "H", "fog_hide": "B", "fog_erase": "E", "shape": "M"}
        groups = (
            ("select", "pan"),
            ("token",),
            ("shape", "portal"),
            ("fog_hide", "fog_erase", "fog_polygon", "fog_select"),
        )
        icons = {
            "select": "cursor",
            "pan": "hand",
            "token": "plus",
            "shape": "shape_circle",
            "portal": "portal",
            "fog_hide": "brush",
            "fog_erase": "eraser",
            "fog_polygon": "fog_polygon",
            "fog_select": "fog_select",
        }
        for section, keys in enumerate(groups):
            if section:
                separator = self.sidebar.addSeparator()
                if section == 3:
                    separator.setObjectName("fogSeparator")
            for key in keys:
                title = LABELS.get(key, "Фигуры")
                action = QAction(tool_icon(icons[key]), title, self)
                action.setCheckable(True)
                action.setToolTip(title + (" · " + shortcuts[key] if key in shortcuts else ""))
                group.addAction(action)
                self.sidebar.addAction(action)
                self.actions[key] = action
                action.triggered.connect(
                    lambda checked=False, k=key: self.choose(
                        self.state.last_shape
                        if k == "shape"
                        else self.state.last_selection
                        if k == "select"
                        else k
                    )
                )
        self.selection_actions = self.add_group(
            "select",
            {"select": "Выбор объектов · V", "vertices": LABELS["vertices"]},
            lambda key: "cursor" if key == "select" else "vertices",
        )
        self.shape_actions = self.add_group("shape", SHAPES, lambda key: "shape_" + key)
        self.context = QWidget(parent)
        self.context.hide()
        self.measurement = QWidget(parent)
        self.measurement.hide()
        measure_layout = QVBoxLayout(self.measurement)
        measure_layout.setContentsMargins(12, 4, 12, 8)
        measure_layout.addWidget(QLabel("Измерение расстояний"))
        self.measurement_mode = measurement_picker(self.measurement, self.view.measurement_mode)
        measure_layout.addWidget(self.measurement_mode)
        layout = QVBoxLayout(self.context)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.help = QLabel()
        self.help.setWordWrap(True)
        for page in (self.help, fog, vectors):
            layout.addWidget(page)
        self.state.changed.connect(self.render)
        view.model_changed.connect(self.model_changed)
        self.render(self.state.active)

    def add_group(self, key, choices, icon_name):
        button = self.sidebar.widgetForAction(self.actions[key])
        menu = ToolMenu(button)
        menu.setToolTipsVisible(True)
        actions = {}
        for value, title in choices.items():
            action = menu.addAction(tool_icon(icon_name(value)), title)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, k=value: self.choose(k))
            actions[value] = action
        self.actions[key].setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        return actions

    def choose(self, tool):
        self.state.activate(tool)
        self.view.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def populate_general(self):
        self.grid = QAction(tool_icon("table"), "Показать сетку", self)
        self.grid.setCheckable(True)
        self.grid.toggled.connect(self.grid_toggled)
        self.general.addAction(self.grid)
        fit = self.general.addAction(tool_icon("fit"), "Вписать карту")
        fit.triggered.connect(
            lambda: self.view.fitInView(self.view.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        )
        settings = self.general.addAction(tool_icon("settings"), "Настройки карты")
        menu = QMenu(self.general)
        menu.addAction("Сетка и масштаб…", self.grid_settings_requested.emit)
        settings.setMenu(menu)
        self.general.widgetForAction(settings).setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.general.addAction(
            tool_icon("monitor"), "Презентация игрокам", self.presentation_requested.emit
        )
        spacer = QWidget(self.general)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.general.addWidget(spacer)
        editor = self.general.addAction(
            tool_icon("rename"), "Редактор карты", self.editor_requested.emit
        )
        button = self.general.widgetForAction(editor)
        button.setObjectName("mapEditorButton")
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.model_changed()

    def model_changed(self):
        if hasattr(self, "grid"):
            grid = getattr(self.view, "grid", None)
            blocker = QSignalBlocker(self.grid)
            self.grid.setChecked(bool(grid and grid.enabled))
            self.grid.setEnabled(grid is not None)
            del blocker
        ready = self.view._background is not None
        for key, action in self.actions.items():
            action.setEnabled(ready or key in {"select", "pan"})

    def render(self, active):
        for key, action in self.actions.items():
            blocker = QSignalBlocker(action)
            action.setChecked(
                active == key
                or (key == "shape" and active in SHAPES)
                or (key == "select" and active == "vertices")
            )
            del blocker
        for key, action in self.shape_actions.items():
            blocker = QSignalBlocker(action)
            action.setChecked(key == self.state.last_shape)
            del blocker
        for key, action in self.selection_actions.items():
            action.setChecked(key == self.state.last_selection)
        self.actions["select"].setIcon(
            tool_icon("vertices" if self.state.last_selection == "vertices" else "cursor")
        )
        self.actions["select"].setToolTip(
            LABELS[self.state.last_selection] + " · Меню — выбор объектов / вершины"
        )
        last = self.state.last_shape
        self.actions["shape"].setIcon(tool_icon("shape_" + last))
        self.actions["shape"].setToolTip(SHAPES[last] + " · M · Меню — другие фигуры")
        self.fog.setVisible(active in FOG)
        self.vectors.setVisible(self.state.vectors_enabled)
        self.help.setVisible(active in {"pan", "token"})
        self.help.setText(HINTS.get(active, ""))
        self.vectors.notice.setText(HINTS.get(active, HINTS["figure"]))
        self.fog.brush_group.setVisible(active in {"fog_hide", "fog_erase"})
        self.fog.notice.setText(
            LABELS.get(active, "")
            + " · "
            + (
                "Enter — завершить · Escape — отменить"
                if active == "fog_polygon"
                else "Escape — отменить · Space — панорама"
            )
        )
