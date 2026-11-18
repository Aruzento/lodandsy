from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QEventLoop, QObject, Qt, Signal
from PySide6.QtGui import QImageReader
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from lodandsy.application.module_session import ModuleSession
from lodandsy.ui.map_widget import MapWidget
from lodandsy.ui.tools_widgets import DiceWidget, RandomTableWidget


def read_map_image(path):
    path = Path(path)
    if path.stat().st_size > 64 * 1024**2:
        raise ValueError("Изображение превышает 64 MiB")
    reader = QImageReader(str(path))
    if bytes(reader.format()).lower() not in {b"png", b"jpeg", b"bmp", b"gif", b"webp"}:
        raise ValueError("Поддерживаются PNG, JPEG, BMP, GIF и WebP")
    size = reader.size()
    if size.width() <= 0 or size.height() <= 0 or size.width() * size.height() > 16_000_000:
        raise ValueError("Изображение должно содержать не более 16 миллионов пикселей")
    image = reader.read()
    if image.isNull():
        raise ValueError("Не удалось прочитать изображение: " + reader.errorString())
    return image


class ModuleController(QObject):
    _result = Signal(object)
    import_finished = Signal()
    busy_changed = Signal()

    def __init__(self, app):
        super().__init__(app.window)
        self.app = app
        self.session = ModuleSession(self)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lodandsy-images")
        self._callbacks = {}
        self._next_job = 0
        self._generation = 0
        self._images = OrderedDict()
        self._map_ui = {}
        self.importing = False
        self._result.connect(self._finish, Qt.ConnectionType.QueuedConnection)
        self.session.map_changed.connect(self._refresh_map)
        self.session.table_changed.connect(self._refresh_table)
        self.session.map_deleted.connect(lambda key: app.window_manager.close_window(f"map:{key}"))
        self.session.table_deleted.connect(
            lambda key: app.window_manager.close_window(f"table:{key}"))
        app.session.cards_deleted.connect(self._refresh_links)
        app.session.card_created.connect(self._refresh_links)
        self.map_menu = app.window.menuBar().addMenu("Карты")
        self.map_menu.aboutToShow.connect(self._map_menu)
        self.tools_menu = app.window.menuBar().addMenu("Инструменты")
        self.tools_menu.aboutToShow.connect(self._tools_menu)

    def _map_menu(self):
        self.map_menu.clear()
        action = self.map_menu.addAction("Создать карту из изображения…", self.request_map)
        action.setEnabled(not self.importing)
        self.map_menu.addSeparator()
        for document in self.session.maps.values():
            self.map_menu.addAction(document.title, lambda key=document.id: self.open_map(key))

    def _tools_menu(self):
        self.tools_menu.clear()
        self.tools_menu.addAction("Кубики", self.open_dice)
        self.tools_menu.addAction("Создать случайную таблицу…", self.request_table)
        self.tools_menu.addSeparator()
        for table in self.session.tables.values():
            self.tools_menu.addAction(table.title, lambda key=table.id: self.open_table(key))

    def _run(self, operation, callback):
        self._next_job += 1
        key = self._next_job
        self._callbacks[key] = (self._generation, callback)
        future = self._executor.submit(operation)
        def completed(job):
            try:
                value, error = job.result(), None
            except Exception as failure:
                value, error = None, str(failure)
            try:
                self._result.emit((key, value, error))
            except RuntimeError:
                pass  # Application was destroyed; immutable files stay unreferenced.
        future.add_done_callback(completed)

    def _finish(self, result):
        key, value, error = result
        generation, callback = self._callbacks.pop(key, (None, None))
        if generation == self._generation and callback is not None:
            callback(value, error)

    def _cache(self, asset_id, image):
        self._images[asset_id] = image
        self._images.move_to_end(asset_id)
        while sum(item.sizeInBytes() for item in self._images.values()) > 64 * 1024**2:
            self._images.popitem(last=False)

    def reset(self, maps=(), tables=()):
        self._generation += 1
        self._images.clear()
        self._map_ui.clear()
        self.session.reset(maps, tables)

    def wait_import(self):
        if self.importing:
            loop = QEventLoop()
            self.import_finished.connect(loop.quit)
            try:
                if self.importing:
                    loop.exec()
            finally:
                self.import_finished.disconnect(loop.quit)

    def shutdown(self):
        self.wait_import()
        self._executor.shutdown(wait=True)

    def request_map(self):
        project = self.app.project_controller
        if project.store is None and not project.save_current():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self.app.window, "Изображение карты", "",
            "Изображения (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        if not filename:
            return
        title, accepted = QInputDialog.getText(self.app.window, "Новая карта", "Название:")
        if accepted and title.strip():
            self.import_map(Path(filename), title)

    def import_map(self, path, title):
        from lodandsy.domain.module_values import validate_title

        title = validate_title(title)
        project = self.app.project_controller
        if self.importing or project.store is None:
            raise ValueError("Дождитесь импорта или выберите проект")
        store = project.store
        self.importing = True
        self.busy_changed.emit()
        self.app.window.statusBar().showMessage("Импорт изображения…")
        def operation():
            # Decode before copying; no DB reference is published until bytes are ready.
            image = read_map_image(path)
            asset = store.import_asset(path)
            # Validate the actual copied bytes if the source changed during import.
            image = read_map_image(store.root / asset.path)
            return asset, image
        def complete(value, error):
            try:
                if error:
                    self._error(error)
                else:
                    asset, image = value
                    project.assets[asset.id] = asset
                    self._cache(asset.id, image)
                    document = self.session.create_map(title, asset.id)
                    self.open_map(document.id)
            finally:
                self.importing = False
                self.app.window.statusBar().clearMessage()
                self.busy_changed.emit()
                self.import_finished.emit()
        self._run(operation, complete)

    def _error(self, error):
        QMessageBox.warning(self.app.window, "Карты и инструменты", str(error))

    def open_dice(self):
        return self.app.window_manager.open_window("dice", "Кубики", DiceWidget)

    def request_table(self):
        title, ok = QInputDialog.getText(self.app.window, "Случайная таблица", "Название:")
        if ok and title.strip():
            self.open_table(self.session.create_table(title).id)

    def open_table(self, table_id):
        table = self.session.get_table(table_id)
        def factory():
            widget = RandomTableWidget()
            widget.set_rows(table.rows)
            widget.rows_changed.connect(lambda rows: self.session.edit_table(table_id, rows=rows))
            widget.rename_requested.connect(lambda: self._rename("table", table_id))
            widget.delete_requested.connect(lambda: self._delete("table", table_id))
            def roll():
                try:
                    index, row = self.session.get_table(table_id).choose()
                    widget.result.setText(f"{index}. {row}")
                    widget.copy.setEnabled(True)
                except ValueError as error:
                    widget.result.setText(str(error))
                    widget.copy.setEnabled(False)
            widget.roll_requested.clicked.connect(roll)
            return widget
        return self.app.window_manager.open_window(f"table:{table_id}", table.title, factory)

    def _refresh_table(self, key):
        window = self.app.window_manager.find_window(f"table:{key}")
        if window:
            table = self.session.get_table(key)
            window.setWindowTitle(table.title)
            window.widget().set_rows(table.rows)

    def open_map(self, map_id):
        document = self.session.get_map(map_id)
        key = f"map:{map_id}"
        existing = self.app.window_manager.find_window(key)
        if existing:
            return self.app.window_manager.focus_window(key)
        def factory():
            widget = MapWidget(self.session.undo_stack(map_id))
            widget.view.pin_moved.connect(
                lambda pin, x, y: self.session.edit_pin(map_id, pin, x=x, y=y))
            widget.view.pin_action.connect(
                lambda pin, action: self._pin_action(map_id, pin, action))
            widget.view.add_requested.connect(lambda x, y: self._add_pin(map_id, x, y))
            widget.add.triggered.connect(lambda: self._add_pin(map_id, .5, .5))
            widget.rename_requested.connect(lambda: self._rename("map", map_id))
            widget.delete_requested.connect(lambda: self._delete("map", map_id))
            return widget
        window = self.app.window_manager.open_window(key, document.title, factory)
        window.closed.connect(
            lambda closed: self._map_ui.update({map_id: closed.widget().pending_camera
                                               or closed.widget().view.camera()}))
        widget = window.widget()
        def loaded(image, error):
            if self.app.window_manager.find_window(key) is not window:
                return
            if error:
                widget.message.setText("Изображение недоступно: " + error)
                widget.view.scene().setSceneRect(0, 0, 1000, 700)
            else:
                self._cache(document.asset_id, image)
                widget.view.set_image(image)
                widget.message.setText("Колесо — масштаб · фон — перемещение · ПКМ — маркеры · "
                                       "двойной щелчок по маркеру — Card")
            self._refresh_map(map_id)
            camera = widget.pending_camera or self._map_ui.get(map_id)
            if camera:
                widget.view.restore_camera(camera)
            widget.pending_camera = None
        image = self._images.get(document.asset_id)
        if image is not None:
            loaded(image, None)
        else:
            project = getattr(self.app, "project_controller", None)
            asset = project.assets.get(document.asset_id) if project else None
            if asset and self.app.project_root:
                path = (self.app.project_root / asset.path).resolve()
                assets_root = (self.app.project_root / "assets").resolve()
                if (assets_root.is_relative_to(self.app.project_root.resolve())
                        and path.is_relative_to(assets_root)):
                    self._run(lambda: read_map_image(path), loaded)
                else:
                    loaded(None, "ресурс находится вне assets проекта")
            else:
                loaded(None, "ресурс отсутствует")
        self._refresh_map(map_id)
        return window

    def _refresh_map(self, key):
        window = self.app.window_manager.find_window(f"map:{key}")
        if window:
            document = self.session.get_map(key)
            window.setWindowTitle(document.title)
            window.widget().view.set_pins(document.pins, {c.id for c in self.app.cards.all()})

    def _refresh_links(self, *_args):
        for key in self.session.maps:
            self._refresh_map(key)

    def _add_pin(self, map_id, x, y):
        title, ok = QInputDialog.getText(self.app.window, "Новый маркер", "Название:")
        if ok and title.strip():
            self.session.add_pin(map_id, title, x, y)

    def _pin_action(self, map_id, pin_id, action):
        pin = next(p for p in self.session.get_map(map_id).pins if p.id == pin_id)
        if action == "delete":
            self.session.delete_pin(map_id, pin_id)
        elif action == "unlink":
            self.session.edit_pin(map_id, pin_id, card_id=None)
        elif action == "open":
            try:
                self.app.open_card_editor(pin.card_id)
            except ValueError:
                self._error("Карточка не связана, удалена или отсутствует. Маркер сохранён.")
        elif action == "rename":
            title, ok = QInputDialog.getText(self.app.window, "Маркер", "Название:", text=pin.title)
            if ok and title.strip():
                self.session.edit_pin(map_id, pin_id, title=title)
        elif action == "create":
            title, ok = QInputDialog.getText(
                self.app.window, "Новая карточка", "Название:", text=pin.title)
            if ok and title.strip():
                card = self.app.create_card(title)
                self.session.edit_pin(map_id, pin_id, card_id=card.id)
                self.app.open_card_editor(card.id)
        elif action == "link":
            cards = self.app.cards.all()
            if not cards:
                self._error("Сначала создайте карточку или выберите «Создать связанную карточку».")
                return
            labels = [f"{card.title} · {card.id}" for card in cards]
            chosen, ok = QInputDialog.getItem(
                self.app.window, "Привязка", "Карточка:", labels, 0, False)
            if ok:
                self.session.edit_pin(map_id, pin_id, card_id=cards[labels.index(chosen)].id)

    def _rename(self, kind, key):
        item = self.session.get_map(key) if kind == "map" else self.session.get_table(key)
        title, ok = QInputDialog.getText(
            self.app.window, "Переименование", "Название:", text=item.title)
        if ok and title.strip():
            operation = self.session.edit_map if kind == "map" else self.session.edit_table
            operation(key, title=title)

    def _delete(self, kind, key):
        if QMessageBox.question(self.app.window, "Удаление", "Удалить карту/таблицу из проекта?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            operation = self.session.delete_map if kind == "map" else self.session.delete_table
            operation(key)
