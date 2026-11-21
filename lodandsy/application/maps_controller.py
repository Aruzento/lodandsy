"""Map viewer/editor lifecycle and native resources; dependencies are explicit public contracts."""

from pathlib import Path
from threading import Event

from PySide6.QtCore import QEventLoop, QObject, Qt, Signal
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QProgressDialog

from lodandsy.application.background_tasks import BackgroundTasks
from lodandsy.application.fog_geometry import state_path
from lodandsy.application.map_pyramid import MAX_SOURCE_BYTES, ensure_pyramid
from lodandsy.application.map_tiles import MapTiles
from lodandsy.ui.map_editor import MapEditorWidget
from lodandsy.ui.map_presentation import MapPresentation
from lodandsy.ui.map_settings_dialogs import MapGridDialog
from lodandsy.ui.map_widget import MapWidget


class MapsController(QObject):
    import_finished = Signal()
    busy_changed = Signal()
    import_progress = Signal(int)

    def __init__(
        self,
        window,
        windows,
        service,
        cards,
        resources,
        media,
        actions,
        open_card,
        ensure_project,
        request_card_creation,
        queries,
    ):
        super().__init__(window)
        self.window, self.windows, self.service, self.cards = window, windows, service, cards
        self.resources, self.media, self.actions = resources, media, actions
        self.open_card, self.ensure_project = open_card, ensure_project
        self.tasks = BackgroundTasks(self, workers=2, name="map-images")
        self.request_card_creation = request_card_creation
        self.queries = queries
        self.tiles = MapTiles(self)
        self._cancel = Event()
        self._decode_cancels = set()
        self.presentations = {}
        self._compiled_fog = {}
        self._map_ui = {}
        self._map_editor_ui = {}
        self._card_maps = {}
        self._actor_maps = {}
        self.show_actor = lambda card_id, actor_id, scale=None: None
        self.update_actor_scale = lambda card_id, actor_id, scale: None
        self.progress = None
        self.importing = False
        service.map_changed.connect(self._refresh_map)
        service.history_blocked.connect(window.show_notice)
        service.map_deleted.connect(self.close_presentation)
        service.map_deleted.connect(lambda key: self.windows.close_window(f"map:{key}"))
        service.map_deleted.connect(lambda key: self.windows.close_window(f"map-editor:{key}"))
        service.core.replaced.connect(self.reset)
        cards.card_created.connect(self.card_changed)
        cards.card_changed.connect(self.card_changed)
        cards.actor_changed.connect(self._actor_changed)

    def reset(self):
        for key in tuple(self.presentations):
            self.close_presentation(key)
        self._cancel.set()
        for cancel in self._decode_cancels:
            cancel.set()
        self._decode_cancels.clear()
        self.tasks.invalidate()
        self.tiles.reset()
        self._map_ui.clear()
        self._map_editor_ui.clear()
        self._card_maps.clear()
        self._actor_maps.clear()
        self._compiled_fog.clear()
        if self.importing:
            if self.progress:
                self.progress.close()
                self.progress.deleteLater()
                self.progress = None
            self.importing = False
            self.busy_changed.emit()
            self.import_finished.emit()

    def shutdown(self):
        for key in tuple(self.presentations):
            self.close_presentation(key)
        self.wait_import()
        for cancel in self._decode_cancels:
            cancel.set()
        self.tasks.shutdown()
        self.tiles.shutdown()

    def capture_ui(self):
        def capture(prefix, saved):
            result = dict(saved)
            for key in self.windows.window_keys():
                if key.startswith(prefix):
                    camera = self.windows.find_window(key).widget().camera_state()
                    if camera is not None:
                        result[key[len(prefix) :]] = camera
            return result

        return {
            "maps": capture("map:", self._map_ui),
            "map_editors": capture("map-editor:", self._map_editor_ui),
        }

    def restore_ui(self, values):
        for name, prefix, saved in [
            ("maps", "map:", self._map_ui),
            ("map_editors", "map-editor:", self._map_editor_ui),
        ]:
            for key, camera in values.get(name, {}).items():
                if key in self.service.maps and isinstance(camera, dict):
                    saved[key] = camera
                    window = self.windows.find_window(prefix + key)
                    if window:
                        window.widget().restore_camera_state(camera)

    def wait_import(self):
        if self.importing:
            loop = QEventLoop()
            self.import_finished.connect(loop.quit)
            try:
                if self.importing:
                    loop.exec()
            finally:
                self.import_finished.disconnect(loop.quit)

    def request_map(self, parent_id=None):
        project = self.resources
        if project.store is None and not self.ensure_project():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self.window,
            "Изображение карты",
            "",
            "Изображения (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
        )
        if not filename:
            return
        title, accepted = QInputDialog.getText(self.window, "Новая карта", "Название:")
        if accepted and title.strip():
            self.import_map(Path(filename), title, parent_id)

    def import_map(self, path, title, parent_id=None):
        from lodandsy.domain.module_values import validate_title

        title = validate_title(title)
        if parent_id is not None:
            self.service.core.entities.get(parent_id)
        project = self.resources
        if self.importing or project.store is None:
            raise ValueError("Дождитесь импорта или выберите проект")
        store = project.store
        known_assets = tuple(project.assets.values())
        self.importing = True
        self._cancel = cancel = Event()
        self.progress = QProgressDialog(
            "Импорт и построение пирамиды…", "Отмена", 0, 100, self.window
        )
        self.progress.setAutoClose(False)
        self.progress.setMinimumDuration(0)
        self.progress.canceled.connect(self._cancel.set)
        self.import_progress.connect(self.progress.setValue)
        self.busy_changed.emit()
        self.window.statusBar().showMessage("Импорт изображения…")

        def operation():
            # Decode before copying; no DB reference is published until bytes are ready.
            asset = store.import_asset(
                path,
                known_assets=known_assets,
                max_bytes=MAX_SOURCE_BYTES,
                cancelled=cancel.is_set,
            )
            pyramid = ensure_pyramid(store.root, asset, cancel, self.import_progress.emit)
            return asset, pyramid

        def complete(value, error):
            try:
                if error:
                    if not self._cancel.is_set():
                        self._error(error)
                else:
                    asset, image = value
                    if parent_id is not None:
                        self.service.core.entities.get(parent_id)
                    project.assets[asset.id] = asset
                    document = self.service.create_map(title, asset.id, parent_id)
                    self.open_map(document.id)
            except (OSError, ValueError) as failure:
                self._error(failure)
            finally:
                self.importing = False
                self.progress.close()
                self.progress.deleteLater()
                self.progress = None
                self.window.statusBar().clearMessage()
                self.busy_changed.emit()
                self.import_finished.emit()

        self.tasks.run(operation, complete)

    def _error(self, error):
        QMessageBox.warning(self.window, "Карты и инструменты", str(error))

    def open_map(self, map_id):
        return self._open_map_view(map_id, False)

    def open_map_editor(self, map_id):
        self.service.initialize_layers(map_id)
        return self._open_map_view(map_id, True)

    def _open_map_view(self, map_id, editor):
        document = self.service.get_map(map_id)
        key = ("map-editor:" if editor else "map:") + map_id
        title = ("Редактор карты · " if editor else "") + document.title
        existing = self.windows.find_window(key)
        if existing:
            return self.windows.focus_window(key)

        def factory():
            widget = (
                MapEditorWidget(
                    self.service.undo_stack(map_id),
                    self.queries,
                    self.asset_size,
                    self.asset_preview,
                )
                if editor
                else MapWidget(self.service.undo_stack(map_id))
            )
            widget.view.transient_changed.connect(
                lambda kind, key, x, y: self._transient(map_id, kind, key, x, y, widget.view)
            )
            widget.project_root = self.resources.root
            self.media.ready.connect(widget.image_ready)
            if editor:
                widget.layer_action.connect(
                    lambda action: self._editor_layer_action(map_id, action)
                )
                widget.layer_edit_requested.connect(
                    lambda key, changes: self._edit_layer(map_id, key, changes)
                )
                widget.object_edit_requested.connect(
                    lambda key, changes: self.service.edit_object(map_id, key, **changes)
                )
                widget.object_delete_requested.connect(
                    lambda key: self.service.delete_object(map_id, key)
                )
                widget.asset_import_requested.connect(lambda: self._editor_import_asset(map_id))
                widget.asset_place_requested.connect(
                    lambda layer, asset, x, y: self._editor_place(map_id, layer, asset, x, y)
                )
                widget.view.object_moved.connect(
                    lambda key, x, y: self.service.edit_object(map_id, key, x=x, y=y)
                )
                widget.view.object_action.connect(
                    lambda key, action: self._editor_object_action(map_id, key, action)
                )
            else:
                widget.fog_tools.edited.connect(
                    lambda path, erase: self._fog_edit(map_id, path, erase, widget)
                )
                widget.fog_tools.deleted.connect(
                    lambda key: self.service.delete_fog_region(map_id, key)
                )
                widget.presentation_requested.connect(lambda: self.open_presentation(map_id))
                widget.view.camera_changed.connect(lambda rect: self._camera_changed(map_id, rect))
                widget.editor_requested.connect(lambda: self.open_map_editor(map_id))
                widget.grid_requested.connect(lambda: self._grid_settings(map_id))
                widget.view.token_moved.connect(
                    lambda token, x, y: self._move_token(map_id, token, x, y, widget.view)
                )
                widget.view.token_action.connect(
                    lambda token, action: self._token_action(map_id, token, action)
                )
                widget.view.token_selected.connect(
                    lambda token: self._select_participant(map_id, token)
                )
                widget.view.token_add_requested.connect(lambda x, y: self._add_token(map_id, x, y))
                widget.view.card_exists = self._is_card
                widget.view.card_dropped.connect(
                    lambda card, x, y: self.service.add_token(map_id, card, x, y)
                )

                def add_token():
                    center = widget.view.mapToScene(widget.view.viewport().rect().center())
                    self._add_token(map_id, center.x(), center.y())

                widget.token_add.triggered.connect(add_token)
            return widget

        window = self.windows.open_window(key, title, factory)
        if not editor:
            window.closed.connect(lambda closed: self.close_presentation(map_id))
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
            if self.windows.find_window(key) is not window:
                return
            if error:
                widget.message.setText("Изображение недоступно: " + error)
            else:
                widget.view.set_pyramid(pyramid, self.tiles)
                presentation = self.presentations.get(map_id)
                if presentation:
                    presentation.view.set_pyramid(pyramid, self.tiles)
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
            if not editor:
                widget.view._publish_camera()

        other = self.windows.find_window(("map:" if editor else "map-editor:") + map_id)
        if other and other.widget().view._background is not None:
            loaded(other.widget().view._background.pyramid, None)
        else:
            project = self.resources
            asset = project.assets.get(document.asset_id)
            if asset and self.resources.root:
                root = self.resources.root
                self.tasks.run(lambda: ensure_pyramid(root, asset, cancel), loaded)
            else:
                loaded(None, "ресурс отсутствует")
        self._refresh_map(map_id)
        return window

    def _fog_edit(self, map_id, path, erase, widget):
        try:
            self.service.edit_fog(map_id, path, erase=erase)
        except ValueError as error:
            widget.fog_tools.notice.setText(str(error))

    def open_presentation(self, map_id):
        existing = self.presentations.get(map_id)
        if existing:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return existing
        viewer = self.windows.find_window("map:" + map_id)
        if viewer is None:
            viewer = self.open_map(map_id)
        document = self.service.get_map(map_id)
        presentation = MapPresentation(document.title)
        self.presentations[map_id] = presentation
        presentation.closed.connect(lambda: self.presentations.pop(map_id, None))
        self.media.ready.connect(presentation.image_ready)
        self._refresh_map(map_id)
        background = viewer.widget().view._background
        if background is not None:
            presentation.view.set_pyramid(background.pyramid, self.tiles)
            viewer.widget().view._publish_camera()
        presentation.show()
        return presentation

    def close_presentation(self, map_id):
        presentation = self.presentations.get(map_id)
        if presentation:
            presentation.close()

    def _camera_changed(self, map_id, rect):
        presentation = self.presentations.get(map_id)
        if presentation:
            presentation.follow_camera(rect)

    def _transient(self, map_id, kind, key, x, y, source):
        views = [
            w.widget().view
            for prefix in ("map:", "map-editor:")
            if (w := self.windows.find_window(prefix + map_id))
        ]
        if map_id in self.presentations:
            views.append(self.presentations[map_id].view)
        for view in views:
            if view is source:
                continue
            item = (
                next((i for i in view._tokens if i.token.id == key), None)
                if kind == "token"
                else view._objects.get(key)
            )
            if item:
                item.setPos(x, y)

    def _remember_map_camera(self, map_id, widget, editor=False):
        camera = widget.camera_state()
        if map_id in self.service.maps and camera is not None:
            (self._map_editor_ui if editor else self._map_ui)[map_id] = camera

        if not any(self.windows.find_window(prefix + map_id) for prefix in ("map:", "map-editor:")):
            self._compiled_fog.pop(map_id, None)

    def _refresh_map(self, key):
        windows = [self.windows.find_window(prefix + key) for prefix in ("map:", "map-editor:")]
        if not any(windows):
            return
        document = self.service.get_map(key)
        cached = self._compiled_fog.get(key)
        if cached is None or cached[0] != document.fog:
            cached = (document.fog, state_path(document.fog))
            self._compiled_fog[key] = cached
        presentation = self.presentations.get(key)
        if presentation:
            presentation.setWindowTitle("Презентация · " + document.title)
            presentation.view.set_annotations(
                document,
                self.cards.get_card,
                self.resources.root,
                self.resources.assets,
                self.media.cached_preview,
                fog_path=cached[1],
            )
        for ids in self._card_maps.values():
            ids.discard(key)
        for ids in self._actor_maps.values():
            ids.discard(key)
        for token in document.tokens:
            self._card_maps.setdefault(token.card_id, set()).add(key)
            if token.actor_id:
                self._actor_maps.setdefault((token.card_id, token.actor_id), set()).add(key)
        project = self.resources
        for window in windows:
            if not window:
                continue
            widget = window.widget()
            editor = isinstance(widget, MapEditorWidget)
            window.setWindowTitle(("Редактор карты · " if editor else "") + document.title)
            widget.view.set_annotations(
                document,
                self.cards.get_card,
                self.resources.root,
                project.assets,
                self.media.cached_preview,
                fog_path=cached[1],
                participant_resolver=self.cards.participant_info,
            )
            if editor:
                widget.set_document(document)
            selected = widget.view.selected_token_id()
            if selected:
                token = next((t for t in document.tokens if t.id == selected), None)
                if token and token.actor_id:
                    self.update_actor_scale(
                        token.card_id, token.actor_id, document.grid.feet_per_cell
                    )

    def _select_participant(self, map_id, token_id):
        token = next((t for t in self.service.get_map(map_id).tokens if t.id == token_id), None)
        if token and token.actor_id:
            self.show_actor(
                token.card_id, token.actor_id, self.service.get_map(map_id).grid.feet_per_cell
            )

    def focus_token(self, map_id, token_id):
        widget = self.open_map(map_id).widget()
        widget.view.select_token(token_id)
        self._select_participant(map_id, token_id)

    def _actor_changed(self, card_id, actor_id, fields):
        try:
            self.cards.participant_info(card_id, actor_id)
        except ValueError:
            return
        for map_id in tuple(self._actor_maps.get((card_id, actor_id), ())):
            for prefix in ("map:", "map-editor:"):
                window = self.windows.find_window(prefix + map_id)
                if window:
                    window.widget().view.refresh_participant(
                        card_id, actor_id, self.cards.participant_info
                    )

    def _edit_layer(self, map_id, key, changes):
        try:
            self.service.edit_layer(map_id, key, **changes)
        except ValueError as error:
            self.window.show_notice(str(error))
            self._refresh_map(map_id)

    def _editor_layer_action(self, map_id, action):
        widget = self.open_map_editor(map_id).widget()
        key = widget.active_layer()
        document = self.service.get_map(map_id)
        if action == "add":
            title, ok = QInputDialog.getText(widget, "Новый слой", "Название:")
            if ok and title.strip():
                layer = self.service.add_layer(map_id, title)
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
            self.service.move_layer(map_id, key, position)
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
                self.service.delete_layer(map_id, key, delete_contents=True)

    def _editor_import_asset(self, map_id):
        source = self._image_filename()
        if not source:
            return

        def publish(asset, error):
            if error:
                self._error(error)
                return False
            if map_id not in self.service.maps:
                return False
            card = self.actions.create_object_card(Path(source).stem, asset.id)
            widget = self.open_map_editor(map_id).widget()
            widget.library_search.clear()
            widget.select_library_card(card.id)
            return True

        self.media.import_image(Path(source), publish)

    def asset_size(self, key):
        asset = self.resources.asset(key)
        return self.media.image_size(self.resources.root, asset.path) if asset else None

    def asset_preview(self, key):
        asset = self.resources.asset(key)
        return self.media.cached_preview(self.resources.root, asset.path) if asset else None

    def _editor_place(self, map_id, layer, card_id, x, y):
        card = self.queries.resolve(card_id, "card", "object")
        size = self.asset_size(card.image_id) if card else None
        if size is None:
            self.window.show_notice("Изображение карточки объекта недоступно")
            return
        scale = 128 / max(size.width(), size.height())
        item = self.service.add_object(
            map_id,
            layer,
            card.image_id,
            x,
            y,
            width=size.width() * scale,
            height=size.height() * scale,
        )
        self.open_map_editor(map_id).widget().select_object(item.id)

    def _editor_object_action(self, map_id, key, action):
        if action == "delete":
            self.service.delete_object(map_id, key)
        else:
            self.open_map_editor(map_id).widget().select_object(key)

    def _grid_settings(self, map_id):
        dialog = MapGridDialog(self.service.get_map(map_id).grid, self.window)
        if dialog.exec():
            self.service.edit_map(map_id, grid=dialog.grid(), command="Изменить сетку")

    def _move_token(self, map_id, token_id, x, y, view):
        window = self.windows.find_window(f"map:{map_id}")
        document = self.service.maps.get(map_id)
        if (
            window is None
            or window.widget().view is not view
            or document is None
            or not any(token.id == token_id for token in document.tokens)
        ):
            return
        self.service.move_token(map_id, token_id, x, y, bounds=(view.map_width, view.map_height))
        token = next(token for token in self.service.get_map(map_id).tokens if token.id == token_id)
        for item in view._tokens:
            if item.token.id == token_id:
                item.setPos(token.x, token.y)

    def _image_filename(self):
        filename, _ = QFileDialog.getOpenFileName(
            self.window,
            "Изображение токена",
            "",
            "Изображения (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
        )
        return filename

    def _is_card(self, key):
        try:
            return self.service.core.entities.get(key).kind == "card"
        except ValueError:
            return False

    def card_changed(self, key, fields=None):
        for map_id in tuple(self._card_maps.get(key, ())):
            if map_id in self.service.maps:
                self._refresh_map(map_id)

    def _add_token(self, map_id, x, y):
        choices = ["Новая карточка…"]
        cards = self.cards.all()
        choices += [f"{c.title} · {c.id[:8]}" for c in cards]
        choice, ok = QInputDialog.getItem(
            self.window, "Разместить карточку", "Карточка:", choices, 0, False
        )
        if not ok:
            return
        if choices.index(choice):
            self.service.add_token(
                map_id, cards[choices.index(choice) - 1].id, max(0, x), max(0, y)
            )
        else:
            title, kind, player, ok = self.request_card_creation(self.window)
            if ok:
                self.create_card_token(
                    map_id, None, title, max(0, x), max(0, y), card_type=kind, player=player
                )

    def create_card_token(
        self, map_id, source, title, x, y, *, card_type="character", player=False
    ):
        self.cards.prepare_card(title, card_type=card_type)
        self.service.get_map(map_id)

        def publish(asset, error):
            if error:
                self._error(error)
                return False
            if map_id not in self.service.maps:
                return False
            token = self.actions.create_card_placement(
                map_id,
                title,
                x,
                y,
                card_type=card_type,
                asset_id=asset.id if asset else None,
                player=player,
            )
            window = self.windows.find_window(f"map:{map_id}")
            if window:
                for item in window.widget().view._tokens:
                    item.setSelected(item.token.id == token.id)
            return True

        if source is None:
            publish(None, None)
        else:
            self.media.import_image(source, publish)

    def _token_action(self, map_id, token_id, action):
        token = next((t for t in self.service.get_map(map_id).tokens if t.id == token_id), None)
        if token is None:
            return
        if action == "delete":
            self.service.delete_token(map_id, token_id)
        elif action == "copy":
            try:
                self.actions.copy_token(map_id, token_id)
            except ValueError as error:
                self._error(str(error))
        elif action == "open":
            try:
                self.cards.get_card(token.card_id)
            except ValueError:
                self._error("Карточка размещения отсутствует")
                return
            self.open_card(token.card_id)
