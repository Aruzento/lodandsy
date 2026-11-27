import shutil
import zipfile
from contextlib import nullcontext
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
)

from lodandsy.application.project_catalogue import ProjectCatalogue
from lodandsy.application.project_history import ProjectHistory
from lodandsy.application.save_coordinator import SaveCoordinator, SaveState
from lodandsy.application.sqlite_project_store import (
    AssetRecord,
    ProjectError,
    ProjectSnapshot,
    SQLiteProjectStore,
)
from lodandsy.application.workspace_state import (
    UI_STATE_NAME,
    capture_workspace,
    load_workspace_file,
    restore_workspace,
    save_workspace_file,
)
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.icons import icon
from lodandsy.ui.theme import apply_role

if TYPE_CHECKING:
    from lodandsy.application.app_controller import AppController


class ProjectController(QObject):
    def __init__(self, controller: "AppController", history=None, catalogue=None):
        super().__init__(controller.window)
        self.controller = controller
        self.history = history if history is not None else ProjectHistory()
        self.catalogue = catalogue if catalogue is not None else ProjectCatalogue()
        controller.attach_project(self)
        self.resources = controller.resources
        self.window = controller.window
        self.store: SQLiteProjectStore | None = None
        self.assets: dict[str, AssetRecord] = {}
        self._ui_restore_failed = False
        self.saver = SaveCoordinator(self._snapshot, self)
        controller.core.committed.connect(self.saver.mark_dirty)
        controller.cards_service.field_draft_changed.connect(self._update_status)
        controller.cards_service.field_edits.pending_changed.connect(self._update_status)
        controller.card_views.pending_changed.connect(self._update_status)
        controller.tables_service.pending_changed.connect(self._update_status)
        controller.tables.wallet_edits.pending_changed.connect(self._update_status)
        controller.actions.title_edits.pending_changed.connect(self._update_status)
        controller.tables_service.draft_changed.connect(self._update_status)
        controller.maps.busy_changed.connect(self._update_status)
        controller.media.busy_changed.connect(self._update_status)
        self.saver.state_changed.connect(self._update_status)
        self.status = QLabel()
        self.retry = QPushButton("Повторить сохранение")
        self.retry.clicked.connect(self.save_current)
        self.window.statusBar().addWidget(self.status, 1)
        self.window.statusBar().addPermanentWidget(self.retry)
        self._build_menu()
        self.window.close_guard = self.can_close
        if self.controller.cards.all():
            self.saver.mark_dirty()
        self._update_status()

    def _build_menu(self):
        menu = self.window.menuBar().addMenu("Проект")
        self.new_action = QAction("Создать проект…", self)
        self.new_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_action.triggered.connect(self._request_new)
        self.open_action = QAction("Открыть проект…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self._request_open)
        self.save_action = QAction("Сохранить", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save_current)
        self.backup_action = QAction("Создать резервную копию…", self)
        self.backup_action.triggered.connect(self._request_backup)
        self.restore_action = QAction("Восстановить резервную копию…", self)
        self.restore_action.triggered.connect(self._request_restore)
        for action in [
            self.new_action,
            self.open_action,
            self.save_action,
        ]:
            menu.addAction(action)
        tools = self.window.menuBar().addMenu("Инструменты")
        dice = tools.addAction("Кубики")
        dice.setIcon(icon("dice"))
        dice.triggered.connect(self.controller.dice.open)
        self.loot_action = tools.addAction("Генератор лута")
        self.loot_action.setIcon(icon("loot"))
        self.loot_action.triggered.connect(self.controller.loot.open)
        self.shop_action = tools.addAction("Магазин")
        self.shop_action.setIcon(icon("shop"))
        self.shop_action.triggered.connect(self.controller.shop.open)

    @property
    def store(self):
        return self.resources.store

    @store.setter
    def store(self, value):
        self.resources.select_store(value)

    @property
    def assets(self):
        return self.resources.assets

    @assets.setter
    def assets(self, value):
        self.resources.assets = value

    @property
    def busy(self):
        return self.controller.maps.importing or self.controller.media.importing

    def _snapshot(self, revision):
        return ProjectSnapshot(
            self.controller.cards.all(),
            revision,
            tuple(self.assets.values()),
            tuple(self.controller.maps_service.maps.values()),
            tuple(self.controller.tables_service.tables.values()),
            self.controller.core.entities.summaries(),
            self.controller.cards_service.rules,
            self.controller.economy.currency,
            self.controller.economy.settings.custom_categories,
        )

    @property
    def draft_count(self):
        return (
            len(self.controller.cards_service.field_drafts)
            + self.controller.tables_service.draft_count
            + len(self.controller.tables.wallet_edits.drafts)
            + len(self.controller.actions.title_edits.drafts)
        )

    def discard_drafts(self):
        session = self.controller.cards_service
        for key in {key for key, field in session.field_drafts}:
            session.discard_field_drafts(key)
        for key in self.controller.tables_service.draft_table_ids:
            self.controller.tables.discard_drafts(key)
        self.controller.tables_service.discard_orphans()
        self.controller.tables.wallet_edits.discard()
        self.controller.actions.title_edits.discard()
        self._update_status()

    def _confirm_drafts(self, *, defer_discard=False):
        if not self.draft_count:
            return True
        dialog = QMessageBox(self.window)
        dialog.setWindowTitle("Несохранённый ошибочный ввод")
        dialog.setText(
            "Корректные данные можно сохранить. Ошибочный ввод остаётся только в текущей сессии."
        )
        fix = dialog.addButton("Исправить", QMessageBox.ButtonRole.ActionRole)
        discard = dialog.addButton(
            "Отбросить ошибочный ввод", QMessageBox.ButtonRole.DestructiveRole
        )
        dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.exec()
        if dialog.clickedButton() is fix:
            session = self.controller.cards_service
            if session.field_drafts:
                address = next(iter(session.field_drafts))
                key, field = address
                if getattr(address, "actor_id", None) is not None:
                    from lodandsy.domain.actor_state import ActorRef

                    self.controller.inspector_binding.show_actor(ActorRef(key, address.actor_id))
                    widget = (
                        self.window.inspector_panel.title_edit
                        if field == "actor_name"
                        else self.window.inspector_panel.field_form.controls.get(field)
                    )
                    if widget:
                        widget.setFocus()
                    return False
                editor = self.controller.open_card_editor(key).widget()
                if field in {s.id for s in session.cards.get(key).sections}:
                    editor.select_section(field)
                elif field == "title":
                    editor.title_edit.setFocus()
                elif field == "summary":
                    editor.summary_edit.setFocus()
                else:
                    widget = self.window.inspector_panel.field_form.controls.get(field)
                    if widget:
                        widget.setFocus()
            elif self.controller.tables_service.draft_table_ids:
                key = self.controller.tables_service.draft_table_ids[0]
                self.controller.tables.open_table(key)
            elif self.controller.tables.wallet_edits.drafts:
                self.controller.tables.focus_wallet_draft()
            elif self.controller.actions.title_edits.drafts:
                key, field = next(iter(self.controller.actions.title_edits.drafts))
                self.controller.core.select(key)
                self.window.inspector_panel.title_edit.setFocus()
            else:
                self.controller.tables.show_orphan_drafts()
            return False
        if dialog.clickedButton() is not discard:
            return False
        if self.saver.dirty and not self.save_current():
            return False
        if not defer_discard:
            self.discard_drafts()
        return True

    def _update_status(self, *_args):
        self.window.right_rail.settings_button.setEnabled(self.store is not None)
        self.controller.rules_action.setEnabled(self.store is not None and not self.busy)
        self.controller.economy_action.setEnabled(self.store is not None and not self.busy)
        self.loot_action.setEnabled(self.store is not None)
        self.shop_action.setEnabled(self.store is not None)
        labels = {
            SaveState.CLEAN: "Сохранено",
            SaveState.DIRTY: "Есть несохранённые изменения",
            SaveState.SAVING: "Сохранение…",
            SaveState.ERROR: "Ошибка сохранения",
        }
        name = self.store.root.name if self.store else "Проект не выбран"
        text = f"{name} — {labels[self.saver.state]}"
        if self.store is None and self.saver.state == SaveState.CLEAN:
            text = "Создайте или откройте проект"
        if self.saver.last_error:
            text += f": {self.saver.last_error}"
        if self.draft_count:
            text += f" · Ошибочный ввод не сохранён: {self.draft_count}"
        pending = (
            self.controller.tables_service.pending_count
            + self.controller.tables.wallet_edits.pending_count
            + self.controller.cards_service.field_edits.pending_count
            + self.controller.card_views.pending_count
            + self.controller.actions.title_edits.pending_count
        )
        if pending:
            text += f" · Незавершённый ввод: {pending}"
        self.status.setText(text)
        role = "error" if self.saver.state == SaveState.ERROR else (
            "warning" if self.saver.dirty or self.draft_count else "empty"
        )
        apply_role(self.status, role)
        self.status.setToolTip(text)
        self.retry.setVisible(self.saver.state == SaveState.ERROR)
        for action in [
            self.new_action,
            self.open_action,
            self.backup_action,
            self.restore_action,
        ]:
            action.setEnabled(not self.saver.saving and not self.busy)
        self.backup_action.setEnabled(
            self.store is not None and not self.saver.saving and not self.busy
        )
        self.restore_action.setEnabled(self.backup_action.isEnabled())
        self.window.setWindowTitle(f"LODANDSY — {name}" + (" *" if self.saver.dirty else ""))

    def _wait_for_edits(self):
        self.controller.flush_edits()
        self.controller.media.wait_import()
        self.controller.maps.wait_import()
        self.saver.wait_current()

    def create_project(self, target: str | Path, *, preserve_current=True, discard=False):
        self._wait_for_edits()
        if (self.draft_count or (self.saver.dirty and self.store is not None)) and not discard:
            raise ProjectError("Save the current project before creating another")
        if not self.controller.may_close_settings():
            return False
        self._save_ui_state()
        initial = self._snapshot(1) if preserve_current and (
            self.controller.cards.all()
            or self.assets
            or self.controller.maps_service.maps
            or self.controller.tables_service.tables
        ) else None
        folder = self.catalogue.reserve(target) if isinstance(target, str) else nullcontext(target)
        with folder as destination:
            store = SQLiteProjectStore.create_new(destination, initial)
        if preserve_current:
            self.controller.close_settings()
            self.controller.reset_catalogue_tools()
            self._select_store(store, initial.revision if initial is not None else 0)
        else:
            self._activate_store(store, save_previous_layout=False)
        return True

    def _check_switch(self, discard):
        self._wait_for_edits()
        if (self.saver.dirty or self.draft_count) and not discard:
            raise ProjectError("Save valid changes, resolve drafts or explicitly discard first")
        if not self.controller.may_close_settings():
            raise ProjectError("Смена проекта отменена. Черновики настроек сохранены в окне.")

    def open_project(self, folder: Path, *, discard=False, expected=None):
        if self.store is not None and self.store.root == Path(folder).resolve():
            return
        self._check_switch(discard)
        store, verified = SQLiteProjectStore.open_with_snapshot(folder, expected=expected)
        self._activate_store(store, verified=verified)

    def restore_project(self, archive: Path, name: str, *, discard=False):
        self._check_switch(discard)
        self._save_ui_state()
        with self.catalogue.reserve(name) as destination:
            try:
                store, verified = SQLiteProjectStore.restore_with_snapshot(archive, destination)
            except zipfile.BadZipFile as error:
                raise ProjectError(f"Повреждена резервная копия: {error}") from error
        self._activate_store(store, verified=verified, save_previous_layout=False)
        return True

    def _activate_store(self, store, *, verified=None, save_previous_layout=True):
        try:
            if verified is None:
                snapshot = store.load()
                entities = snapshot.entity_collection()
            else:
                snapshot, entities = verified.snapshot, verified.entities
            cards = CardCollection(entities=entities)
            if save_previous_layout:
                self._save_ui_state()
        except Exception:
            store.close()
            raise
        self.controller.replace_cards(cards)
        self.assets = {asset.id: asset for asset in snapshot.assets}
        self._select_store(store, snapshot.revision)
        try:
            state = load_workspace_file(store.root)
            if state is not None:
                restore_workspace(self.controller, state)
        except (OSError, ValueError, TypeError, AttributeError) as error:
            self._ui_restore_failed = True
            self._show_error(error)

    def _select_store(self, store, revision):
        previous = self.store
        self.store = store
        self.controller.set_project_root(store.root)
        self.saver.reset(revision, store.save)
        self._ui_restore_failed = False
        if previous is not None:
            previous.close()
        self.history.remember(store.root)
        self._update_status()

    def save_current(self) -> bool:
        self.controller.flush_edits()
        self.controller.media.wait_import()
        if self.store is None:
            return self._name_project(
                self.window, lambda name: self.create_project(name, preserve_current=True)
            )
        return self.saver.save()

    def _confirm_changes(self, *, defer_discard=False) -> bool:
        self._wait_for_edits()
        if not self._confirm_drafts(defer_discard=defer_discard):
            return False
        if not self.saver.dirty:
            return True
        choice = QMessageBox.warning(
            self.window,
            "Несохранённые изменения",
            "Сохранить изменения текущего проекта?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self.save_current()
        return choice == QMessageBox.StandardButton.Discard

    def can_close(self):
        if not self.controller.may_close_settings():
            return False
        if not self._confirm_changes():
            return False
        try:
            self._save_ui_state()
        except OSError as error:
            self._show_error(error)
            return False
        self.saver.shutdown()
        self.controller.shutdown_features()
        if self.store is not None:
            self.store.close()
        return True

    def _save_ui_state(self):
        if self.store is None:
            return
        if self._ui_restore_failed and (self.store.root / UI_STATE_NAME).exists():
            shutil.copy2(
                self.store.root / UI_STATE_NAME,
                self.store.root / f".ui-state-unreadable-{uuid4().hex}.json",
            )
        save_workspace_file(self.store.root, capture_workspace(self.controller))
        self._ui_restore_failed = False

    def _show_error(self, error):
        QMessageBox.warning(self.window, "Проект", str(error))

    def _request_new(self, _checked=False, *, parent=None):
        host = parent if parent is not None else self.window
        return self._name_project(
            host,
            lambda name: self._confirm_changes(defer_discard=True)
            and self.create_project(name, preserve_current=False, discard=True),
        )

    def _name_project(self, host, submit, **options):
        from lodandsy.ui.project_name_dialog import ProjectNameDialog

        dialog = ProjectNameDialog(self.catalogue.destination, submit, host, **options)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def choose_project(self, *, welcome=False):
        from lodandsy.ui.project_chooser import ProjectChooser

        try:
            root = self.catalogue.root
            entries = self.catalogue.entries(self.history.entries)
            catalogue_error = ""
        except (OSError, ValueError) as error:
            root, entries = "", ()
            catalogue_error = f"Не удалось прочитать каталог проектов.\n{error}"
        dialog = ProjectChooser(
            entries, None if welcome else self.window, welcome=welcome, root=root,
        )
        if catalogue_error:
            dialog.error.setText(catalogue_error)

        def selected(folder, expected=None):
            try:
                same = self.store is not None and self.store.root == Path(folder).resolve()
                if not same and not self._confirm_changes(defer_discard=True):
                    return
                self.open_project(Path(folder), discard=True, expected=expected)
            except (OSError, ValueError) as error:
                dialog.error.setText("Не удалось открыть проект.\n" + str(error))
                return
            self.window.show()
            dialog.accept()

        def browse():
            folder = QFileDialog.getExistingDirectory(
                dialog, "Открыть папку проекта", self.history.last_directory
            )
            if folder:
                selected(folder)

        def create():
            if self._request_new(parent=dialog):
                self.window.show()
                dialog.accept()

        expected_projects = {entry["path"]: entry.get("metadata") for entry in entries}
        dialog.open_requested.connect(
            lambda folder: selected(folder, expected_projects.get(folder))
        )
        dialog.browse_requested.connect(browse)
        dialog.create_requested.connect(create)
        return dialog.exec()

    def _request_open(self):
        self.choose_project()

    def _request_backup(self):
        if not self.save_current() or self.store is None:
            return
        parent = self.controller.settings_window or self.window
        dialog = QFileDialog(parent, "Резервная копия")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setNameFilter("LODANDSY backup (*.lodbackup)")
        dialog.setDefaultSuffix("lodbackup")
        if dialog.exec():
            filename = dialog.selectedFiles()[0]
            try:
                self.store.backup(Path(filename))
                self.window.statusBar().showMessage("Резервная копия создана", 5000)
            except (OSError, ValueError) as error:
                self._show_error(error)

    def _request_restore(self):
        host = self.controller.settings_window or self.window
        filename, _ = QFileDialog.getOpenFileName(
            host, "Восстановить копию", "", "LODANDSY backup (*.lodbackup)"
        )
        if filename:
            archive = Path(filename)
            self._name_project(
                self.window,
                lambda name: self._confirm_changes(defer_discard=True)
                and self.restore_project(archive, name, discard=True),
                restoring=True,
                suggestion=archive.stem,
            )
