from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from PySide6.QtCore import QEventLoop, QObject, Qt, Signal
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QProgressDialog

from lodandsy.application.map_pyramid import MAX_SOURCE_BYTES, ensure_pyramid
from lodandsy.application.map_tiles import MapTiles
from lodandsy.application.module_session import ModuleSession
from lodandsy.ui.map_settings_dialogs import MapGridDialog, TokenPropertiesDialog
from lodandsy.ui.map_widget import MapWidget
from lodandsy.ui.tools_widgets import DiceWidget, RandomTableWidget


class ModuleController(QObject):
    _result = Signal(object)
    import_finished = Signal()
    busy_changed = Signal()
    import_progress = Signal(int)

    def __init__(self, app):
        super().__init__(app.window)
        self.app = app
        self.session = ModuleSession(self)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lodandsy-images")
        self._callbacks = {}
        self._next_job = 0
        self._generation = 0
        self.tiles = MapTiles(self)
        self._cancel = Event()
        self._decode_cancels = set()
        self.progress = None
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

    def request_create(self, kind):
        if kind == "map":
            self.request_map()
        elif kind == "table":
            self.request_table()
        else:
            raise ValueError("Unsupported module kind")

    def request_rename(self, kind, key):
        self._rename(kind, key)

    def request_delete(self, kind, key):
        self._delete(kind, key)

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

    def reset(self, maps=(), tables=()):
        for cancel in self._decode_cancels:
            cancel.set()
        self._decode_cancels.clear()
        self._generation += 1
        self.tiles.reset()
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
        for cancel in self._decode_cancels:
            cancel.set()
        self._executor.shutdown(wait=True)
        self.tiles.shutdown()

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
        known_assets = tuple(project.assets.values())
        self.importing = True
        self._cancel.clear()
        self.progress = QProgressDialog("Импорт и построение пирамиды…", "Отмена", 0, 100,
                                        self.app.window)
        self.progress.setAutoClose(False)
        self.progress.setMinimumDuration(0)
        self.progress.canceled.connect(self._cancel.set)
        self.import_progress.connect(self.progress.setValue)
        self.busy_changed.emit()
        self.app.window.statusBar().showMessage("Импорт изображения…")
        def operation():
            # Decode before copying; no DB reference is published until bytes are ready.
            asset = store.import_asset(path, known_assets=known_assets, max_bytes=MAX_SOURCE_BYTES,
                                       cancelled=self._cancel.is_set)
            pyramid = ensure_pyramid(store.root, asset, self._cancel, self.import_progress.emit)
            return asset, pyramid
        def complete(value, error):
            try:
                if error:
                    if not self._cancel.is_set():
                        self._error(error)
                else:
                    asset, image = value
                    project.assets[asset.id] = asset
                    document = self.session.create_map(title, asset.id)
                    self.open_map(document.id)
            finally:
                self.importing = False
                self.progress.close()
                self.progress.deleteLater()
                self.progress = None
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
            widget.project_root = self.app.project_root
            self.app.card_images.ready.connect(widget.image_ready)
            widget.grid_requested.connect(lambda: self._grid_settings(map_id))
            widget.view.token_moved.connect(
                lambda token, x, y: self._move_token(map_id, token, x, y, widget.view))
            widget.view.token_action.connect(
                lambda token, action: self._token_action(map_id, token, action))
            widget.view.token_add_requested.connect(lambda x, y: self._add_token(map_id, x, y))
            def add_token():
                center = widget.view.mapToScene(widget.view.viewport().rect().center())
                self._add_token(map_id, center.x(), center.y())
            widget.token_add.triggered.connect(add_token)
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
        window.closed.connect(lambda closed: self._remember_map_camera(map_id, closed.widget()))
        widget = window.widget()
        cancel = Event()
        self._decode_cancels.add(cancel)
        window.closed.connect(lambda _closed: cancel.set())
        self.tiles.failed.connect(widget.message.setText)
        def loaded(image, error):
            self._decode_cancels.discard(cancel)
            if self.app.window_manager.find_window(key) is not window:
                return
            if error:
                widget.message.setText("Изображение недоступно: " + error)
                widget.view.scene().setSceneRect(0, 0, 1000, 700)
            else:
                self.tiles.errors.clear()
                widget.view.set_pyramid(image, self.tiles)
                widget.token_add.setEnabled(True)
                widget.message.setText("Колесо — масштаб · фон — перемещение · ПКМ — маркеры · "
                                       "двойной щелчок по маркеру — Card")
            self._refresh_map(map_id)
            camera = widget.pending_camera or self._map_ui.get(map_id)
            if camera:
                widget.view.restore_camera(camera)
            widget.pending_camera = None
        project = getattr(self.app, "project_controller", None)
        asset = project.assets.get(document.asset_id) if project else None
        if asset and self.app.project_root:
            root = self.app.project_root
            self._run(lambda: ensure_pyramid(root, asset, cancel), loaded)
        else:
            loaded(None, "ресурс отсутствует")
        self._refresh_map(map_id)
        return window

    def _remember_map_camera(self, map_id, widget):
        state = widget.camera_state()
        if map_id in self.session.maps and state is not None:
            self._map_ui[map_id] = state

    def _refresh_map(self, key):
        window = self.app.window_manager.find_window(f"map:{key}")
        if window:
            document = self.session.get_map(key)
            window.setWindowTitle(document.title)
            window.widget().view.set_pins(document.pins, {c.id for c in self.app.cards.all()})
            project = getattr(self.app, "project_controller", None)
            window.widget().view.set_annotations(document, {c.id for c in self.app.cards.all()},
                self.app.project_root, project.assets if project else {},
                self.app.card_images.cached_preview)

    def _grid_settings(self, map_id):
        dialog = MapGridDialog(self.session.get_map(map_id).grid, self.app.window)
        if dialog.exec():
            self.session.edit_map(map_id, grid=dialog.grid(), command="Изменить сетку")

    def _move_token(self, map_id, token_id, x, y, view):
        window = self.app.window_manager.find_window(f"map:{map_id}")
        document = self.session.maps.get(map_id)
        if (window is None or window.widget().view is not view or document is None
                or not any(token.id == token_id for token in document.tokens)):
            return
        self.session.move_token(map_id, token_id, x, y,
                                bounds=(view.map_width, view.map_height))
        token = next(token for token in self.session.get_map(map_id).tokens if token.id == token_id)
        for item in view._tokens:
            if item.token.id == token_id:
                item.setPos(token.x, token.y)  # Snap back also when the command is a no-op.

    def _image_filename(self):
        filename, _ = QFileDialog.getOpenFileName(self.app.window, "Изображение токена", "",
            "Изображения (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
        return filename

    def _add_token(self, map_id, x, y):
        if self.app.card_images.importing:
            self.app.window.show_notice("Дождитесь завершения импорта изображения")
            return
        filename = self._image_filename()
        if not filename:
            return
        title, ok = QInputDialog.getText(self.app.window, "Новый токен", "Название:")
        if ok and title.strip():
            self.import_token(map_id, Path(filename), title, x, y)

    def import_token(self, map_id, source, title, x, y):
        from lodandsy.domain.module_values import validate_title
        title = validate_title(title)
        document = self.session.get_map(map_id)
        window = self.app.window_manager.find_window(f"map:{map_id}")
        view = window.widget().view if window else None
        if document.grid.snap:
            x, y = document.grid.snap_point(x, y)
        if view:
            x, y = max(0, min(view.map_width, x)), max(0, min(view.map_height, y))
        def publish(asset, error):
            if error:
                self._error(error)
                return False
            if map_id not in self.session.maps:
                return False
            size = document.grid.cell_size if document.grid.enabled else 64
            token = self.session.add_token(map_id, title, asset.id, x, y, width=size, height=size)
            if view and self.app.window_manager.find_window(f"map:{map_id}") is window:
                for item in view._tokens:
                    item.setSelected(item.token.id == token.id)
            return True
        self.app.card_images.import_image(source, publish)

    def _token_action(self, map_id, token_id, action):
        token = next((t for t in self.session.get_map(map_id).tokens if t.id == token_id), None)
        if token is None:
            return
        if action == "delete":
            self.session.delete_token(map_id, token_id)
        elif action == "unlink":
            self.session.edit_token(map_id, token_id, card_id=None)
        elif action == "open":
            try:
                self.app.open_card_editor(token.card_id)
            except ValueError:
                self._error("Карточка не связана, удалена или отсутствует. Токен сохранён.")
        elif action == "properties":
            dialog = TokenPropertiesDialog(token, self.app.cards.all(), self.app.window)
            if dialog.exec():
                self.session.edit_token(map_id, token_id, **dialog.changes())
        elif action == "create":
            title, ok = QInputDialog.getText(self.app.window, "Новая карточка", "Название:",
                                           text=token.title)
            if ok and title.strip():
                card = self.app.create_card(title)
                self.session.edit_token(map_id, token_id, card_id=card.id)
                self.app.open_card_editor(card.id)
        elif action == "image":
            if self.app.card_images.importing:
                self.app.window.show_notice("Дождитесь завершения импорта изображения")
                return
            filename = self._image_filename()
            if not filename:
                return
            def publish(asset, error):
                if error:
                    self._error(error)
                    return False
                current = self.session.maps.get(map_id)
                if current is None or not any(t.id == token_id for t in current.tokens):
                    return False
                self.session.edit_token(map_id, token_id, asset_id=asset.id)
                return True
            self.app.card_images.import_image(Path(filename), publish)

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
