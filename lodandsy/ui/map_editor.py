"""A map construction surface sharing the viewer's domain/session/tiles, never a second map."""

from PySide6.QtCore import QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSplitter,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.ui.icons import icon
from lodandsy.ui.map_library import ObjectLibraryModel
from lodandsy.ui.map_widget import MapView, MapWidget


class MapEditorWidget(QWidget):
    layer_action = Signal(str)
    layer_edit_requested = Signal(str, object)
    object_edit_requested = Signal(str, object)
    object_delete_requested = Signal(str)
    asset_import_requested = Signal()
    asset_place_requested = Signal(str, str, float, float)

    def __init__(self, undo_stack, queries, image_size, image_provider):
        super().__init__()
        self.setObjectName("mapEditorPage")
        self.document = None
        self.project_root = None
        self.pending_camera = None
        self.view = MapView("editor")
        self.view.set_tool("select")
        self.view.scene().selectionChanged.connect(self._selection_changed)
        self.view.world_clicked.connect(self._place)
        self.message = QLabel(
            "Выбор — выделить/перетащить · Пробел/панорама — перемещение · Escape — отмена жеста"
        )
        self.message.setWordWrap(True)
        self.message.setObjectName("mapStatus")
        bar = QToolBar(self)
        bar.setOrientation(Qt.Orientation.Vertical)
        self.tool_rail = bar
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for title, name, ico in [
            ("Выделить / переместить", "select", "cursor"),
            ("Панорама", "pan", "hand"),
            ("Разместить ресурс", "place", "plus"),
        ]:
            button = QToolButton()
            button.setIcon(icon(ico))
            button.setToolTip(title)
            button.setAccessibleName(title)
            button.setCheckable(True)
            button.setChecked(name == "select")
            group.addButton(button)
            button.clicked.connect(lambda checked=False, n=name: self.view.set_tool(n))
            bar.addWidget(button)
            self.view.tool_changed.connect(lambda tool, b=button, n=name: b.setChecked(tool == n))
        bar.addSeparator()
        MapWidget.add_undo_actions(self, bar, undo_stack)
        fit = bar.addAction(icon("fit"), "Вся карта")
        fit.triggered.connect(
            lambda: self.view.fitInView(self.view.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        )
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.addWidget(QLabel("Слои"))
        self.layers = QListWidget()
        self.layers.setAccessibleName("Слои карты")
        self.layers.itemChanged.connect(self._layer_changed)
        self.layers.currentRowChanged.connect(self._layer_actions)
        left_layout.addWidget(self.layers, 2)
        layer_bar = QToolBar()
        layer_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.layer_actions = {}
        for title, name, ico in [
            ("Новый слой", "add", "plus"),
            ("Выше", "up", "up"),
            ("Ниже", "down", "down"),
            ("Удалить слой", "delete", "delete"),
        ]:
            action = layer_bar.addAction(icon(ico), title)
            action.triggered.connect(lambda checked=False, n=name: self.layer_action.emit(n))
            self.layer_actions[name] = action
        left_layout.addWidget(layer_bar)
        left_layout.addWidget(QLabel("Библиотека объектов"))
        self.library_search = QLineEdit()
        self.library_search.setPlaceholderText("Найти объект…")
        self.library_search.setAccessibleName("Поиск объектов по названию или другому имени")
        left_layout.addWidget(self.library_search)
        self.assets = QListView()
        self.assets.setAccessibleName("Карточки объектов с изображениями")
        self.assets.setIconSize(QSize(48, 48))
        self.library_model = ObjectLibraryModel(queries, image_size, image_provider, self)
        self.assets.setModel(self.library_model)
        self._library_selection = None
        self.library_model.modelAboutToBeReset.connect(self._remember_library_selection)
        self.library_model.modelReset.connect(
            lambda: self.select_library_card(self._library_selection)
        )
        self.library_search.textChanged.connect(self._search_library)
        left_layout.addWidget(self.assets, 3)
        import_button = QToolButton()
        import_button.setText("Импорт изображения…")
        import_button.setIcon(icon("plus"))
        import_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        import_button.clicked.connect(self.asset_import_requested)
        left_layout.addWidget(import_button)
        self.properties = QWidget()
        form = QFormLayout(self.properties)
        form.setContentsMargins(12, 12, 12, 12)
        self.selection_title = QLabel("Выберите объект на карте")
        form.addRow(self.selection_title)
        self.controls = {}
        for key, label, low, high in [
            ("x", "X", 0, 1e9),
            ("y", "Y", 0, 1e9),
            ("width", "Ширина", 0.01, 1e7),
            ("height", "Высота", 0.01, 1e7),
            ("rotation", "Поворот", -360, 360),
            ("z", "Порядок", 0, 9999),
        ]:
            box = QDoubleSpinBox()
            box.setRange(low, high)
            box.setDecimals(0 if key == "z" else 2)
            box.setAccessibleName(label)
            box.editingFinished.connect(self._apply_properties)
            form.addRow(label, box)
            self.controls[key] = box
        remove = QToolButton()
        remove.setIcon(icon("delete"))
        remove.setText("Удалить объект")
        remove.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        remove.clicked.connect(self._delete_selected)
        form.addRow(remove)
        self._selected = None
        left_layout.addWidget(self.properties)
        side_scroll = QScrollArea()
        side_scroll.setFrameShape(QFrame.Shape.NoFrame)
        side_scroll.setWidgetResizable(True)
        side_scroll.setWidget(left)
        side_scroll.setMinimumWidth(180)
        self.sidebar = side_scroll
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        canvas = QHBoxLayout()
        canvas.setContentsMargins(0, 0, 0, 0)
        canvas.setSpacing(0)
        canvas.addWidget(bar)
        canvas.addWidget(self.view, 1)
        center_layout.addLayout(canvas, 1)
        center_layout.addWidget(self.message)
        self.splitter = QSplitter()
        self.splitter.addWidget(center)
        self.splitter.addWidget(side_scroll)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([800, 230])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)
        delete = QAction("Удалить объект", self.view)
        delete.setShortcut("Delete")
        delete.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        delete.triggered.connect(self._delete_selected)
        self.view.addAction(delete)
        self._selection_changed()

    def active_layer(self):
        item = self.layers.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def set_document(self, document):
        self.document = document
        current = self.active_layer()
        old = [
            (
                self.layers.item(i).data(Qt.ItemDataRole.UserRole),
                self.layers.item(i).text(),
                self.layers.item(i).checkState(),
            )
            for i in range(self.layers.count())
        ]
        values = [
            (
                layer.id,
                layer.title,
                Qt.CheckState.Checked if layer.visible else Qt.CheckState.Unchecked,
            )
            for layer in reversed(document.layers)
        ]
        if old != values:
            blocker = QSignalBlocker(self.layers)
            self.layers.clear()
            for key, title, state in values:
                item = QListWidgetItem(title)
                item.setData(Qt.ItemDataRole.UserRole, key)
                item.setFlags(
                    item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(state)
                self.layers.addItem(item)
                if key == current:
                    self.layers.setCurrentItem(item)
            if self.layers.currentRow() < 0 and self.layers.count():
                self.layers.setCurrentRow(0)
            del blocker
        self._layer_actions()
        self._selection_changed()

    def _layer_actions(self, *_):
        row, count = self.layers.currentRow(), self.layers.count()
        self.layer_actions["up"].setEnabled(row > 0)
        self.layer_actions["down"].setEnabled(0 <= row < count - 1)
        self.layer_actions["delete"].setEnabled(row >= 0)

    def _remember_library_selection(self):
        self._library_selection = self.assets.currentIndex().data(Qt.ItemDataRole.UserRole)

    def select_library_card(self, key):
        if key in self.library_model.ids:
            self.assets.setCurrentIndex(self.library_model.index(self.library_model.ids.index(key)))
        elif self.library_model.ids:
            self.assets.setCurrentIndex(self.library_model.index(0))

    def _search_library(self, text):
        self._remember_library_selection()
        self.library_model.filter(text)
        self.select_library_card(self._library_selection)

    def _layer_changed(self, item):
        self.layer_edit_requested.emit(
            item.data(Qt.ItemDataRole.UserRole),
            {"title": item.text(), "visible": item.checkState() == Qt.CheckState.Checked},
        )

    def _selection_changed(self):
        selected = [item for item in self.view.scene().selectedItems() if hasattr(item, "value")]
        self._selected = selected[0].value.id if selected else None
        item = (
            next((o for o in self.document.objects if o.id == self._selected), None)
            if self.document
            else None
        )
        self.properties.setVisible(item is not None)
        self.selection_title.setText("Изображение на карте" if item else "Выберите объект на карте")
        for key, box in self.controls.items():
            blocker = QSignalBlocker(box)
            box.setEnabled(item is not None)
            if item:
                box.setValue(getattr(item, key))
            del blocker

    def _apply_properties(self):
        if self._selected:
            self.object_edit_requested.emit(
                self._selected,
                {
                    key: int(box.value()) if key == "z" else box.value()
                    for key, box in self.controls.items()
                },
            )

    def _delete_selected(self):
        if self._selected:
            self.object_delete_requested.emit(self._selected)

    def select_object(self, key):
        for identity, item in self.view._objects.items():
            item.setSelected(identity == key)

    def _place(self, x, y):
        card = self.assets.currentIndex().data(Qt.ItemDataRole.UserRole)
        layer = self.active_layer()
        if layer and card:
            self.asset_place_requested.emit(layer, card, x, y)
        else:
            self.message.setText("Выберите слой и карточку объекта в библиотеке")

    def image_ready(self, root, name):
        if root == self.project_root:
            self.library_model.images_changed()
            self.view.viewport().update()

    camera_state = MapWidget.camera_state
    restore_camera_state = MapWidget.restore_camera_state
