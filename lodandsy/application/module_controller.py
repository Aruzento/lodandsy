from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from weakref import WeakSet

from PySide6.QtCore import QEventLoop, QObject, Qt, Signal
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QProgressDialog
from shiboken6 import isValid

from lodandsy.application.map_pyramid import MAX_SOURCE_BYTES, ensure_pyramid
from lodandsy.application.map_tiles import MapTiles
from lodandsy.application.module_session import ModuleSession
from lodandsy.ui.dice_widget import DiceWidget
from lodandsy.ui.map_editor import MapEditorWidget
from lodandsy.ui.map_settings_dialogs import MapGridDialog, TokenPropertiesDialog
from lodandsy.ui.map_widget import MapWidget
from lodandsy.ui.table_widget import TableWidget


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
        self._map_editor_ui = {}
        self._card_maps = {}
        app.session.deletion_planners.append(self.session.plan_delete)
        app.window.tree_panel.deletion_reference_count = self.session.placement_count
        self._table_drafts = {}
        self._table_views = {}
        self._draft_snapshots = {}
        self._table_ui = {}
        self._dice_runtime = {}
        self.importing = False
        self._result.connect(self._finish, Qt.ConnectionType.QueuedConnection)
        self.session.map_changed.connect(self._refresh_map)
        self.session.table_changed.connect(self._refresh_table)
        self.session.map_deleted.connect(lambda key: app.window_manager.close_window(f"map:{key}"))
        self.session.map_deleted.connect(
            lambda key: app.window_manager.close_window(f"map-editor:{key}")
        )
        self.session.table_deleted.connect(
            lambda key: app.window_manager.close_window(f"table:{key}")
        )
        app.session.entities_deleted.connect(self.session.notify_deleted)
        self.session.table_deleted.connect(lambda key: self._table_drafts.pop(key, None))
        self.session.table_deleted.connect(lambda key: self._table_ui.pop(key, None))
        app.session.entity_changed.connect(self._entity_changed)
        app.session.entity_created.connect(self._new_entity)
        app.session.entities_deleted.connect(lambda keys: self._refresh_embedded_links())
        app.session.card_created.connect(self._card_created)
        app.session.card_changed.connect(lambda key, fields: self._card_created(key))

    def request_create(self, kind, parent_id=None):
        if kind == "map":
            self.request_map(parent_id)
        elif kind == "table":
            self.request_table(parent_id)
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
        self._map_editor_ui.clear()
        self._card_maps.clear()
        self._table_drafts.clear()
        self._table_views.clear()
        self._draft_snapshots.clear()
        self._table_ui.clear()
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

    def open_dice(self):
        return self.app.window_manager.open_window(
            "tool:dice", "Кубики", lambda: DiceWidget(self._dice_runtime)
        )

    def _entity_changed(self, key, fields):
        kind = self.app.session.entities.get(key).kind
        if kind == "map":
            self.session.map_changed.emit(key)
        elif kind == "table":
            self.session.table_changed.emit(key)

    def request_table(self, parent_id=None):
        title, ok = QInputDialog.getText(self.app.window, "Новая таблица", "Название:")
        if ok and title.strip():
            self.open_table(self.session.create_table(title, parent_id).id)

    def open_table(self, table_id):
        table = self.session.get_table(table_id)

        def factory():
            widget = self.table_view(table_id)
            return widget

        window = self.app.window_manager.open_window(f"table:{table_id}", table.title, factory)
        window.widget().restore_ui(self._table_ui.get(table_id, {}))
        if not getattr(window, "table_ui_connected", False):
            window.closed.connect(
                lambda closed: self._table_ui.update({table_id: closed.widget().ui_state()})
            )
            window.table_ui_connected = True
        return window

    def _new_entity(self, key):
        if self.app.session.entities.get(key).kind == "table":
            self.session.table_changed.emit(key)

    def table_view(self, key):
        widget = TableWidget(self.session.get_table(key), self._table_drafts.setdefault(key, {}))
        self._table_views.setdefault(key, WeakSet()).add(widget)
        widget.document_changed.connect(self.session.update_table)
        widget.draft_changed.connect(lambda: self._table_draft_changed(key))
        widget.setProperty("table_id", key)
        return widget

    def _table_draft_changed(self, key):
        current = self._table_drafts.get(key, {})
        before = self._draft_snapshots.get(key, {})
        changed = {
            cell for cell in current.keys() | before.keys() if current.get(cell) != before.get(cell)
        }
        self._draft_snapshots[key] = dict(current)
        for widget in tuple(self._table_views.get(key, ())):
            if not isValid(widget):
                continue
            widget.update_draft_notice()
            rows = {r.id: i for i, r in enumerate(widget.model.document.rows)}
            cols = {c.id: i for i, c in enumerate(widget.model.document.columns)}
            for row, col in changed:
                if row in rows and col in cols:
                    index = widget.model.index(rows[row], cols[col])
                    widget.model.dataChanged.emit(index, index)
        self.app.project_controller._update_status()

    def embedded_table(self, card_id, section, previous=None):
        if section.table_id is None:
            return None
        try:
            entity = self.app.session.entities.get(section.table_id)
            if entity.kind != "table" or entity.parent_id != card_id:
                return None
            if (
                previous is not None
                and isValid(previous)
                and previous.property("table_id") == section.table_id
            ):
                return previous
            return self.table_view(section.table_id)
        except ValueError:
            return None

    def _refresh_embedded_links(self, key=None):
        for editor in self.app.card_editors.values():
            try:
                card = self.app.cards.get(editor.card_id)
            except ValueError:
                continue
            if editor._model and any(
                s.kind == "table_ref" and (key is None or s.table_id == key)
                for s in editor._model.sections
            ):
                editor.set_canonical(card, self.app.session.field_drafts)

    def _refresh_table(self, key):
        table = self.session.get_table(key)
        window = self.app.window_manager.find_window(f"table:{key}")
        if window:
            window.setWindowTitle(table.title)
        for widget in tuple(self._table_views.get(key, ())):
            if isValid(widget):
                widget.set_document(table)
        self._refresh_embedded_links(key)

    def open_map(self, map_id):
        return self._open_map_view(map_id, False)

    def open_map_editor(self, map_id):
        return self._open_map_view(map_id, True)

    def _open_map_view(self, map_id, editor):
        document = self.session.get_map(map_id)
        key = ("map-editor:" if editor else "map:") + map_id
        title = ("Редактор карты · " if editor else "") + document.title
        existing = self.app.window_manager.find_window(key)
        if existing:
            return self.app.window_manager.focus_window(key)

        def factory():
            widget = (
                MapEditorWidget(self.session.undo_stack(map_id))
                if editor
                else MapWidget(self.session.undo_stack(map_id))
            )
            widget.project_root = self.app.project_root
            self.app.card_images.ready.connect(widget.image_ready)
            if editor:
                widget.asset_provider = lambda key: (
                    self.app.card_images.cached_preview(
                        self.app.project_root, self.app.project_controller.assets[key].path
                    )
                    if key in self.app.project_controller.assets
                    else None
                )
                widget.asset_size = lambda key: (
                    self.app.card_images.image_size(
                        self.app.project_root, self.app.project_controller.assets[key].path
                    )
                    if key in self.app.project_controller.assets
                    else None
                )
                widget.layer_action.connect(
                    lambda action: self._editor_layer_action(map_id, action)
                )
                widget.layer_edit_requested.connect(
                    lambda key, changes: self._edit_layer(map_id, key, changes)
                )
                widget.object_edit_requested.connect(
                    lambda key, changes: self.session.edit_object(map_id, key, **changes)
                )
                widget.object_delete_requested.connect(
                    lambda key: self.session.delete_object(map_id, key)
                )
                widget.asset_import_requested.connect(lambda: self._editor_import_asset(map_id))
                widget.asset_place_requested.connect(
                    lambda layer, asset, x, y: self._editor_place(map_id, layer, asset, x, y)
                )
                widget.view.object_moved.connect(
                    lambda key, x, y: self.session.edit_object(map_id, key, x=x, y=y)
                )
                widget.view.object_action.connect(
                    lambda key, action: self._editor_object_action(map_id, key, action)
                )
            else:
                widget.editor_requested.connect(lambda: self.open_map_editor(map_id))
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
            return widget

        window = self.app.window_manager.open_window(key, title, factory)
        window.closed.connect(
            lambda closed: self._remember_map_camera(map_id, closed.widget(), editor)
        )
        widget = window.widget()
        cancel = Event()
        self._decode_cancels.add(cancel)
        window.closed.connect(lambda closed: cancel.set())
        self.tiles.failed.connect(widget.message.setText)

        def loaded(pyramid, error):
            self._decode_cancels.discard(cancel)
            if self.app.window_manager.find_window(key) is not window:
                return
            if error:
                widget.message.setText("Изображение недоступно: " + error)
            else:
                widget.view.set_pyramid(pyramid, self.tiles)
                if not editor:
                    widget.token_add.setEnabled(True)
                widget.message.setText(
                    "Выбор / панорама / размещение · Escape — отмена жеста"
                    if editor
                    else "Колесо — масштаб · фон — перемещение · двойной щелчок — карточка"
                )
            self._refresh_map(map_id)
            cameras = self._map_editor_ui if editor else self._map_ui
            camera = widget.pending_camera or cameras.get(map_id)
            if camera:
                widget.view.restore_camera(camera)
            widget.pending_camera = None

        other = self.app.window_manager.find_window(("map:" if editor else "map-editor:") + map_id)
        if other and other.widget().view._background is not None:
            loaded(other.widget().view._background.pyramid, None)
        else:
            project = self.app.project_controller
            asset = project.assets.get(document.asset_id)
            if asset and self.app.project_root:
                root = self.app.project_root
                self._run(lambda: ensure_pyramid(root, asset, cancel), loaded)
            else:
                loaded(None, "ресурс отсутствует")
        self._refresh_map(map_id)
        return window

    def _remember_map_camera(self, map_id, widget, editor=False):
        camera = widget.camera_state()
        if map_id in self.session.maps and camera is not None:
            (self._map_editor_ui if editor else self._map_ui)[map_id] = camera

    def _refresh_map(self, key):
        windows = [
            self.app.window_manager.find_window(prefix + key) for prefix in ("map:", "map-editor:")
        ]
        if not any(windows):
            return
        document = self.session.get_map(key)
        for ids in self._card_maps.values():
            ids.discard(key)
        for token in document.tokens:
            self._card_maps.setdefault(token.card_id, set()).add(key)
        project = self.app.project_controller
        for window in windows:
            if not window:
                continue
            widget = window.widget()
            editor = isinstance(widget, MapEditorWidget)
            window.setWindowTitle(("Редактор карты · " if editor else "") + document.title)
            widget.view.set_annotations(
                document,
                self.app.cards.get,
                self.app.project_root,
                project.assets,
                self.app.card_images.cached_preview,
            )
            if editor:
                widget.set_document(document, project.assets)

    def _edit_layer(self, map_id, key, changes):
        try:
            self.session.edit_layer(map_id, key, **changes)
        except ValueError as error:
            self.app.window.show_notice(str(error))
            self._refresh_map(map_id)

    def _editor_layer_action(self, map_id, action):
        widget = self.open_map_editor(map_id).widget()
        key = widget.active_layer()
        document = self.session.get_map(map_id)
        if action == "add":
            title, ok = QInputDialog.getText(widget, "Новый слой", "Название:")
            if ok and title.strip():
                layer = self.session.add_layer(map_id, title)
                for i in range(widget.layers.count()):
                    if widget.layers.item(i).data(Qt.ItemDataRole.UserRole) == layer.id:
                        widget.layers.setCurrentRow(i)
            return
        layer = next((layer for layer in document.layers if layer.id == key), None)
        if not layer:
            return
        if action in {"up", "down"}:
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

    def _editor_import_asset(self, map_id):
        source = self._image_filename()
        if not source:
            return

        def publish(asset, error):
            if error:
                self._error(error)
                return False
            if map_id not in self.session.maps:
                return False
            self._refresh_map(map_id)
            widget = self.open_map_editor(map_id).widget()
            for i in range(widget.assets.count()):
                if widget.assets.item(i).data(Qt.ItemDataRole.UserRole) == asset.id:
                    widget.assets.setCurrentRow(i)
            return True

        self.app.card_images.import_image(Path(source), publish)

    def _editor_place(self, map_id, layer, asset, x, y):
        item = self.session.add_object(map_id, layer, asset, x, y)
        self.open_map_editor(map_id).widget().select_object(item.id)

    def _editor_object_action(self, map_id, key, action):
        if action == "delete":
            self.session.delete_object(map_id, key)
        else:
            self.open_map_editor(map_id).widget().select_object(key)

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
            title, kind, ok = CardCreationDialog.get_card(self.app.window)
            if ok:
                self.create_card_token(map_id, None, title, max(0, x), max(0, y), card_type=kind)

    def create_card_token(self, map_id, source, title, x, y, *, card_type="character"):
        from lodandsy.domain.card import Card, Portrait

        candidate = Card(title, card_type=card_type)
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
