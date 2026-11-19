from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from PySide6.QtCore import QEventLoop, QObject, Qt, Signal
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QProgressDialog

from lodandsy.application.map_pyramid import MAX_SOURCE_BYTES, ensure_pyramid
from lodandsy.application.map_tiles import MapTiles
from lodandsy.application.module_session import ModuleSession
from lodandsy.ui.dice_widget import DiceWidget
from lodandsy.ui.map_settings_dialogs import MapGridDialog, MapObjectDialog, TokenPropertiesDialog
from lodandsy.ui.map_widget import MapWidget
from lodandsy.ui.table_widget import RandomTableWidget


class ModuleController(QObject):
    _result = Signal(object)
    import_finished = Signal()
    busy_changed = Signal()
    import_progress = Signal(int)

    def __init__(self, app):
        super().__init__(app.window)
        self.app = app
        self.session = ModuleSession(
            self, entities=app.session.entities, delete_handler=app.session.delete_entity
        )
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lodandsy-images")
        self._callbacks = {}
        self._next_job = 0
        self._generation = 0
        self.tiles = MapTiles(self)
        self._cancel = Event()
        self._decode_cancels = set()
        self.progress = None
        self._map_ui = {}
        self._card_maps = {}
        app.session.deletion_planners.append(self.session.plan_delete)
        app.window.tree_panel.deletion_reference_count = self.session.placement_count
        self._table_drafts = {}
        self._table_ui = {}
        self._dice_runtime = {}
        self.importing = False
        self._result.connect(self._finish, Qt.ConnectionType.QueuedConnection)
        self.session.map_changed.connect(self._refresh_map)
        self.session.table_changed.connect(self._refresh_table)
        self.session.map_deleted.connect(lambda key: app.window_manager.close_window(f"map:{key}"))
        self.session.table_deleted.connect(
            lambda key: app.window_manager.close_window(f"table:{key}")
        )
        self.session.dice_changed.connect(self._refresh_dice)
        self.session.dice_deleted.connect(
            lambda key: app.window_manager.close_window(f"dice:{key}")
        )
        app.session.entities_deleted.connect(self.session.notify_deleted)
        self.session.table_deleted.connect(lambda key: self._table_drafts.pop(key, None))
        self.session.table_deleted.connect(lambda key: self._table_ui.pop(key, None))
        self.session.dice_deleted.connect(lambda key: self._dice_runtime.pop(key, None))
        app.session.entity_changed.connect(self._entity_changed)
        app.session.card_created.connect(self._card_created)
        app.session.card_changed.connect(lambda key, fields: self._card_created(key))

    def request_create(self, kind, parent_id=None):
        if kind == "map":
            self.request_map(parent_id)
        elif kind == "table":
            self.request_table(parent_id)
        elif kind == "dice":
            title, ok = QInputDialog.getText(self.app.window, "Новые кубики", "Название:")
            if ok and title.strip():
                self.open_dice(self.session.create_dice(title, parent_id).id)
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

    def reset(self):
        for cancel in self._decode_cancels:
            cancel.set()
        self._decode_cancels.clear()
        self._generation += 1
        self.tiles.reset()
        self._map_ui.clear()
        self._card_maps.clear()
        self._table_drafts.clear()
        self._table_ui.clear()
        self._dice_runtime.clear()
        self.session.reset(entities=self.app.session.entities)

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

    def request_map(self, parent_id=None):
        project = self.app.project_controller
        if project.store is None and not project.save_current():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self.app.window,
            "Изображение карты",
            "",
            "Изображения (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
        )
        if not filename:
            return
        title, accepted = QInputDialog.getText(self.app.window, "Новая карта", "Название:")
        if accepted and title.strip():
            self.import_map(Path(filename), title, parent_id)

    def import_map(self, path, title, parent_id=None):
        from lodandsy.domain.module_values import validate_title

        title = validate_title(title)
        if parent_id is not None:
            self.app.session.entities.get(parent_id)
        project = self.app.project_controller
        if self.importing or project.store is None:
            raise ValueError("Дождитесь импорта или выберите проект")
        store = project.store
        known_assets = tuple(project.assets.values())
        self.importing = True
        self._cancel.clear()
        self.progress = QProgressDialog(
            "Импорт и построение пирамиды…", "Отмена", 0, 100, self.app.window
        )
        self.progress.setAutoClose(False)
        self.progress.setMinimumDuration(0)
        self.progress.canceled.connect(self._cancel.set)
        self.import_progress.connect(self.progress.setValue)
        self.busy_changed.emit()
        self.app.window.statusBar().showMessage("Импорт изображения…")

        def operation():
            # Decode before copying; no DB reference is published until bytes are ready.
            asset = store.import_asset(
                path,
                known_assets=known_assets,
                max_bytes=MAX_SOURCE_BYTES,
                cancelled=self._cancel.is_set,
            )
            pyramid = ensure_pyramid(store.root, asset, self._cancel, self.import_progress.emit)
            return asset, pyramid

        def complete(value, error):
            try:
                if error:
                    if not self._cancel.is_set():
                        self._error(error)
                else:
                    asset, image = value
                    if parent_id is not None:
                        self.app.session.entities.get(parent_id)
                    project.assets[asset.id] = asset
                    document = self.session.create_map(title, asset.id, parent_id)
                    self.open_map(document.id)
            except (OSError, ValueError) as failure:
                self._error(failure)
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

    def open_dice(self, key=None):
        if key is None:
            key = next(iter(self.session.dice), None)
            if key is None:
                key = self.session.create_dice("Кубики").id
        document = self.session.get_dice(key)

        def factory():
            widget = DiceWidget(document, self._dice_runtime.setdefault(key, {}))
            widget.document_changed.connect(
                lambda value: self.session.edit_dice(key, presets=value.presets)
            )
            return widget

        return self.app.window_manager.open_window(f"dice:{key}", document.title, factory)

    def _refresh_dice(self, key):
        window = self.app.window_manager.find_window(f"dice:{key}")
        if window:
            document = self.session.get_dice(key)
            window.setWindowTitle(document.title)
            window.widget().set_document(document)

    def _entity_changed(self, key, fields):
        kind = self.app.session.entities.get(key).kind
        if kind == "map":
            self.session.map_changed.emit(key)
        elif kind == "table":
            self.session.table_changed.emit(key)
        elif kind == "dice":
            self.session.dice_changed.emit(key)

    def request_table(self, parent_id=None):
        title, ok = QInputDialog.getText(self.app.window, "Случайная таблица", "Название:")
        if ok and title.strip():
            self.open_table(self.session.create_table(title, parent_id).id)

    def open_table(self, table_id):
        table = self.session.get_table(table_id)

        def factory():
            widget = RandomTableWidget(table, self._table_drafts.setdefault(table_id, {}))
            widget.document_changed.connect(self.session.update_table)
            widget.draft_changed.connect(self.app.project_controller.saver.mark_dirty)
            widget.rename_requested.connect(lambda: self._rename("table", table_id))
            widget.delete_requested.connect(lambda: self._delete("table", table_id))

            def roll():
                try:
                    index, row = self.session.get_table(table_id).choose()
                    widget.result.setText(
                        f"{index}. {self.session.get_table(table_id).row_text(row)}"
                    )
                    widget.copy.setEnabled(True)
                except ValueError as error:
                    widget.result.setText(str(error))
                    widget.copy.setEnabled(False)

            widget.roll_requested.clicked.connect(roll)
            return widget

        window = self.app.window_manager.open_window(f"table:{table_id}", table.title, factory)
        window.widget().restore_ui(self._table_ui.get(table_id, {}))
        if not getattr(window, "table_ui_connected", False):
            window.closed.connect(
                lambda closed: self._table_ui.update({table_id: closed.widget().ui_state()})
            )
            window.table_ui_connected = True
        return window

    def _refresh_table(self, key):
        window = self.app.window_manager.find_window(f"table:{key}")
        if window:
            table = self.session.get_table(key)
            window.setWindowTitle(table.title)
            window.widget().set_document(table)

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
            widget.layer_action.connect(lambda action: self._layer_action(map_id, action))
            widget.mode_changed.connect(lambda: self._refresh_map(map_id))
            widget.view.object_moved.connect(
                lambda key, x, y: self.session.edit_object(map_id, key, x=x, y=y)
            )
            widget.view.object_action.connect(
                lambda key, action: self._object_action(map_id, key, action)
            )
            widget.grid_requested.connect(lambda: self._grid_settings(map_id))
            widget.view.token_moved.connect(
                lambda token, x, y: self._move_token(map_id, token, x, y, widget.view)
            )
            widget.view.token_action.connect(
                lambda token, action: self._token_action(map_id, token, action)
            )
            widget.view.token_add_requested.connect(lambda x, y: self._add_token(map_id, x, y))
            widget.view.card_exists = self._is_card
            widget.view.card_dropped.connect(
                lambda card, x, y: self.session.add_token(map_id, card, x, y)
            )

            def add_token():
                center = widget.view.mapToScene(widget.view.viewport().rect().center())
                self._add_token(map_id, center.x(), center.y())

            widget.token_add.triggered.connect(add_token)
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
                widget.message.setText(
                    "Колесо — масштаб · фон — перемещение · ПКМ — токены · "
                    "двойной щелчок по токену — документ"
                )
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
            for ids in self._card_maps.values():
                ids.discard(key)
            for token in document.tokens:
                self._card_maps.setdefault(token.card_id, set()).add(key)
            window.setWindowTitle(document.title)
            window.widget().set_layers(document.layers)
            project = getattr(self.app, "project_controller", None)
            window.widget().view.set_annotations(
                document,
                self.app.cards.get,
                self.app.project_root,
                project.assets if project else {},
                self.app.card_images.cached_preview,
            )

    def _layer_action(self, map_id, action):
        document = self.session.get_map(map_id)
        widget = self.app.window_manager.find_window(f"map:{map_id}").widget()
        key = widget.layers.currentData()
        layer = next((layer for layer in document.layers if layer.id == key), None)
        if action == "add":
            title, ok = QInputDialog.getText(widget, "Новый слой", "Название:")
            if ok and title.strip():
                layer = self.session.add_layer(map_id, title)
                widget.layers.setCurrentIndex(widget.layers.findData(layer.id))
            return
        if layer is None:
            self.app.window.show_notice("Сначала создайте слой")
            return
        if action == "rename":
            title, ok = QInputDialog.getText(widget, "Название слоя", "Название:", text=layer.title)
            if ok and title.strip():
                self.session.edit_layer(map_id, key, title=title)
        elif action == "visible":
            self.session.edit_layer(map_id, key, visible=not layer.visible)
        elif action in {"up", "down"}:
            position = max(
                0, min(len(document.layers) - 1, layer.position + (1 if action == "up" else -1))
            )
            self.session.move_layer(map_id, key, position)
        elif action == "delete":
            count = sum(o.layer_id == key for o in (*document.objects, *document.tokens))
            if (
                QMessageBox.question(
                    widget,
                    "Удалить слой",
                    f"Удалить слой «{layer.title}» и его объекты ({count})?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                == QMessageBox.StandardButton.Yes
            ):
                self.session.delete_layer(map_id, key, delete_contents=True)
        elif action in {"place", "import"}:
            center = widget.view.mapToScene(widget.view.viewport().rect().center())
            x, y = max(0, center.x()), max(0, center.y())

            def place(asset, error):
                if error:
                    self._error(error)
                    return False
                current = self.session.maps.get(map_id)
                if current is None or not any(layer.id == key for layer in current.layers):
                    return False
                self.session.add_object(map_id, key, asset.id, x, y)
                return True

            if action == "import":
                source = self._image_filename()
                if source:
                    self.app.card_images.import_image(Path(source), place)
            else:
                assets = list(self.app.project_controller.assets.values())
                labels = [a.path for a in assets]
                if not labels:
                    self.app.window.show_notice("В проекте пока нет изображений")
                    return
                choice, ok = QInputDialog.getItem(
                    widget, "Разместить asset", "Изображение:", labels, 0, False
                )
                if ok:
                    place(assets[labels.index(choice)], None)

    def _object_action(self, map_id, key, action):
        item = next((o for o in self.session.get_map(map_id).objects if o.id == key), None)
        if item is None:
            return
        if action == "delete":
            self.session.delete_object(map_id, key)
        else:
            dialog = MapObjectDialog(item, self.app.window)
            if dialog.exec():
                self.session.edit_object(map_id, key, **dialog.changes())

    def _grid_settings(self, map_id):
        dialog = MapGridDialog(self.session.get_map(map_id).grid, self.app.window)
        if dialog.exec():
            self.session.edit_map(map_id, grid=dialog.grid(), command="Изменить сетку")

    def _move_token(self, map_id, token_id, x, y, view):
        window = self.app.window_manager.find_window(f"map:{map_id}")
        document = self.session.maps.get(map_id)
        if (
            window is None
            or window.widget().view is not view
            or document is None
            or not any(token.id == token_id for token in document.tokens)
        ):
            return
        self.session.move_token(map_id, token_id, x, y, bounds=(view.map_width, view.map_height))
        token = next(token for token in self.session.get_map(map_id).tokens if token.id == token_id)
        for item in view._tokens:
            if item.token.id == token_id:
                item.setPos(token.x, token.y)  # Snap back also when the command is a no-op.

    def _image_filename(self):
        filename, _ = QFileDialog.getOpenFileName(
            self.app.window,
            "Изображение токена",
            "",
            "Изображения (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
        )
        return filename

    def _is_card(self, key):
        try:
            return self.app.session.entities.get(key).kind == "card"
        except ValueError:
            return False

    def _card_created(self, key):
        for map_id in tuple(self._card_maps.get(key, ())):
            if map_id in self.session.maps:
                self._refresh_map(map_id)

    def _add_token(self, map_id, x, y):
        from lodandsy.ui.card_creation_dialog import CardCreationDialog

        choices = ["Новая карточка…"]
        cards = self.app.cards.all()
        choices += [f"{c.title} · {c.id[:8]}" for c in cards]
        choice, ok = QInputDialog.getItem(
            self.app.window, "Разместить карточку", "Карточка:", choices, 0, False
        )
        if not ok:
            return
        if choices.index(choice):
            self.session.add_token(
                map_id, cards[choices.index(choice) - 1].id, max(0, x), max(0, y)
            )
        else:
            title, template, kind, ok = CardCreationDialog.get_card(self.app.window)
            if ok:
                self.create_card_token(
                    map_id, None, title, max(0, x), max(0, y), card_type=kind, template_id=template
                )

    def create_card_token(
        self, map_id, source, title, x, y, *, card_type="character", template_id="empty"
    ):
        from lodandsy.domain.card import Card, Portrait

        candidate = Card(title, card_type=card_type, template_id=template_id)
        self.session.get_map(map_id)

        def publish(asset, error):
            if error:
                self._error(error)
                return False
            if map_id not in self.session.maps:
                return False
            from dataclasses import replace

            card = replace(candidate, portrait=Portrait(asset.id)) if asset else candidate
            token = self.session.add_card_placement(card, map_id, x, y)
            self.app.session.card_created.emit(card.id)
            window = self.app.window_manager.find_window(f"map:{map_id}")
            if window:
                for item in window.widget().view._tokens:
                    item.setSelected(item.token.id == token.id)
            return True

        if source is None:
            publish(None, None)
        else:
            self.app.card_images.import_image(source, publish)

    def _token_action(self, map_id, token_id, action):
        from lodandsy.domain.map_document import resolve_token

        token = next((t for t in self.session.get_map(map_id).tokens if t.id == token_id), None)
        if token is None:
            return
        if action == "delete":
            self.session.delete_token(map_id, token_id)
            return
        if action == "reset":
            self.session.edit_token(
                map_id,
                token_id,
                label_override=None,
                image_override=None,
                kind_override=None,
                cells_w=None,
                cells_h=None,
            )
            return
        try:
            card = self.app.cards.get(token.card_id)
        except ValueError:
            self._error("Карточка размещения отсутствует. Удалите повреждённое размещение.")
            return
        if action == "open":
            self.app.open_card_editor(card.id)
        elif action == "rename":
            title, ok = QInputDialog.getText(
                self.app.window, "Карточка", "Название:", text=card.title
            )
            if ok and title.strip():
                self.app.session.update_card_fields(card.id, {"title": title})
        elif action == "properties":
            dialog = TokenPropertiesDialog(token, resolve_token(token, card), self.app.window)
            if dialog.exec():
                self.session.edit_token(map_id, token_id, **dialog.changes())
        elif action == "image":
            window = self.app.open_card_editor(card.id)
            self.app.card_images.portrait(window.widget())
        elif action == "override-image":
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
                self.session.edit_token(map_id, token_id, image_override=asset.id)
                return True

            self.app.card_images.import_image(Path(filename), publish)

    def _rename(self, kind, key):
        item = self.app.session.entities.get(key)
        title, ok = QInputDialog.getText(
            self.app.window, "Переименование", "Название:", text=item.title
        )
        if ok and title.strip():
            self.app.session.update_entity(key, title=title)

    def _delete(self, kind, key):
        panel = self.app.window.tree_panel
        panel.request_delete(panel.tree_model.index_for_node(f"{kind}:{key}"))
