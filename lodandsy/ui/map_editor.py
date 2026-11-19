"""A map construction surface sharing the viewer's domain/session/tiles, never a second map."""

from collections import OrderedDict

from PySide6.QtCore import QPoint, QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.ui.icons import icon
from lodandsy.ui.map_widget import MapView, MapWidget


class MapEditorWidget(QWidget):
    layer_action = Signal(str)
    layer_edit_requested = Signal(str, object)
    object_edit_requested = Signal(str, object)
    object_delete_requested = Signal(str)
    asset_import_requested = Signal()
    asset_place_requested = Signal(str, str, float, float)

    def __init__(self, undo_stack):
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
        left_layout.addWidget(self.layers, 2)
        layer_bar = QToolBar()
        for title, name, ico in [
            ("Новый слой", "add", "plus"),
            ("Выше", "up", "up"),
            ("Ниже", "down", "down"),
            ("Удалить слой", "delete", "delete"),
        ]:
            action = layer_bar.addAction(icon(ico), title)
            action.triggered.connect(lambda checked=False, n=name: self.layer_action.emit(n))
        left_layout.addWidget(layer_bar)
        left_layout.addWidget(QLabel("Ресурсы проекта"))
        self.assets = QListWidget()
        self.assets.setAccessibleName("Палитра изображений проекта")
        self.assets.setIconSize(QSize(48, 48))
        self.asset_provider = lambda key: None
        self.asset_size = lambda key: None
        self._icons = OrderedDict()
        self.assets.verticalScrollBar().valueChanged.connect(lambda: self.refresh_palette())
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
        self._asset_ids = ()
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.addWidget(bar)
        center_layout.addWidget(self.message)
        center_layout.addWidget(self.view, 1)
        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(self.properties)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([190, 800, 200])
        left.setMinimumWidth(140)
        self.properties.setMinimumWidth(150)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        delete = QAction("Удалить объект", self.view)
        delete.setShortcut("Delete")
        delete.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        delete.triggered.connect(self._delete_selected)
        self.view.addAction(delete)
        self._selection_changed()

    def active_layer(self):
        item = self.layers.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def set_document(self, document, assets):
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
            for layer in document.layers
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
        ids = tuple((a.id, a.path) for a in assets.values())
        if self._asset_ids != ids:
            current = (
                self.assets.currentItem().data(Qt.ItemDataRole.UserRole)
                if self.assets.currentItem()
                else None
            )
            self._icons.clear()
            self.assets.clear()
            self._asset_ids = ids
            for key, path in ids:
                if self.asset_size(key) is None:
                    continue
                item = QListWidgetItem(path.rsplit("/", 1)[-1][:20])
                item.setToolTip(path)
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.assets.addItem(item)
                if key == current:
                    self.assets.setCurrentItem(item)
            if self.assets.currentRow() < 0 and self.assets.count():
                self.assets.setCurrentRow(0)
        self.refresh_palette()
        self._selection_changed()

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
        asset = self.assets.currentItem()
        layer = self.active_layer()
        if layer and asset:
            self.asset_place_requested.emit(layer, asset.data(Qt.ItemDataRole.UserRole), x, y)
        else:
            self.message.setText("Выберите слой и ресурс в палитре")

    def image_ready(self, root, name):
        if root == self.project_root:
            self.refresh_palette()
            self.view.viewport().update()

    def refresh_palette(self):
        start = max(0, self.assets.indexAt(QPoint(2, 2)).row())
        for i in range(start, min(self.assets.count(), start + 24)):
            item = self.assets.item(i)
            key = item.data(Qt.ItemDataRole.UserRole)
            if key in self._icons:
                continue
            image = self.asset_provider(key)
            if image is not None and not image.isNull():
                item.setIcon(
                    QIcon(
                        QPixmap.fromImage(image).scaled(
                            48,
                            48,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                )
                self._icons[key] = item
        while len(self._icons) > 128:
            key, item = self._icons.popitem(last=False)
            item.setIcon(QIcon())

    camera_state = MapWidget.camera_state
    restore_camera_state = MapWidget.restore_camera_state
