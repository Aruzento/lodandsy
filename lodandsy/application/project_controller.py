import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
)

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

if TYPE_CHECKING:
    from lodandsy.application.app_controller import AppController


class ProjectController(QObject):
    def __init__(self, controller: "AppController"):
        super().__init__(controller.window)
        self.controller = controller
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
        from lodandsy.application.mow_import_controller import MowImportController

        self.mow_importer = MowImportController(self)
        self.mow_importer.busy_changed.connect(self._update_status)
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
            self.backup_action,
            self.restore_action,
        ]:
            menu.addAction(action)
        self.mow_actions = []
        for title, directory in [("Импорт карточки MOW…", False), ("Импорт каталога MOW…", True)]:
            action = menu.addAction(title)
            action.triggered.connect(
                lambda checked=False, d=directory: self.mow_importer.request(d)
            )
            self.mow_actions.append(action)
        tools = self.window.menuBar().addMenu("Инструменты")
        dice = tools.addAction("Кубики")
        dice.triggered.connect(self.controller.dice.open)

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
        return (
            self.controller.maps.importing
            or self.controller.media.importing
            or (hasattr(self, "mow_importer") and self.mow_importer.importing)
        )

    def _snapshot(self, revision):
        return ProjectSnapshot(
            self.controller.cards.all(),
            revision,
            tuple(self.assets.values()),
            tuple(self.controller.maps_service.maps.values()),
            tuple(self.controller.tables_service.tables.values()),
            self.controller.core.entities.summaries(),
        )

    @property
    def draft_count(self):
        return (
            len(self.controller.cards_service.field_drafts)
            + self.controller.tables_service.draft_count
            + len(self.controller.actions.title_edits.drafts)
        )

    def discard_drafts(self):
        session = self.controller.cards_service
        for key in {key for key, field in session.field_drafts}:
            session.discard_field_drafts(key)
        for key in self.controller.tables_service.draft_table_ids:
            self.controller.tables.discard_drafts(key)
        self.controller.tables_service.discard_orphans()
        self.controller.actions.title_edits.discard()
        self._update_status()

    def _confirm_drafts(self):
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
                key, field = next(iter(session.field_drafts))
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
        self.discard_drafts()
        return True

    def _update_status(self, *_args):
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
            + self.controller.cards_service.field_edits.pending_count
            + self.controller.card_views.pending_count
            + self.controller.actions.title_edits.pending_count
        )
        if pending:
            text += f" · Незавершённый ввод: {pending}"
        self.status.setText(text)
        color = (
            "#f19a9a"
            if self.saver.state == SaveState.ERROR
            else ("#ceb075" if self.saver.dirty or self.draft_count else "#aab7ca")
        )
        self.status.setStyleSheet(f"color: {color};")
        self.status.setToolTip(text)
        self.retry.setVisible(self.saver.state == SaveState.ERROR)
        for action in [
            self.new_action,
            self.open_action,
            self.backup_action,
            self.restore_action,
            *self.mow_actions,
        ]:
            action.setEnabled(not self.saver.saving and not self.busy)
        self.window.setWindowTitle(f"LODANDSY — {name}" + (" *" if self.saver.dirty else ""))

    def create_project(self, folder: Path, *, preserve_current=True, discard=False):
        self.controller.flush_edits()
        self.controller.media.wait_import()
        self.controller.maps.wait_import()
        self.mow_importer.wait_import()
        self.saver.wait_current()
        if (self.draft_count or (self.saver.dirty and self.store is not None)) and not discard:
            raise ProjectError("Save the current project before creating another")
        store = SQLiteProjectStore.create(folder)
        old = self.store
        if old is not None:
            try:
                self._save_ui_state()
            except Exception:
                store.close()
                raise
        self.store = store
        self._ui_restore_failed = False
        self.controller.set_project_root(store.root)
        if not preserve_current:
            self.controller.replace_cards(CardCollection())
            self.assets.clear()
        self.saver.reset(0, store.save)
        if (
            self.controller.cards.all()
            or self.assets
            or self.controller.maps_service.maps
            or self.controller.tables_service.tables
        ):
            self.saver.mark_dirty()
            if not self.saver.save():
                # Keep the selected project and dirty in-memory data available for retry.
                if old is not None:
                    old.close()
                return False
        if old is not None:
            old.close()
        self._update_status()
        return True

    def open_project(self, folder: Path, *, discard=False):
        self.controller.flush_edits()
        self.controller.media.wait_import()
        self.controller.maps.wait_import()
        self.mow_importer.wait_import()
        self.saver.wait_current()
        if self.store is not None and self.store.root == Path(folder).resolve():
            return
        if (self.saver.dirty or self.draft_count) and not discard:
            raise ProjectError("Save valid changes, resolve drafts or explicitly discard first")
        store = SQLiteProjectStore.open(folder)
        try:
            snapshot = store.load()
            cards = CardCollection(entities=snapshot.entity_collection())
        except Exception:
            store.close()
            raise
        previous = self.store
        if previous is not None:
            try:
                self._save_ui_state()
            except Exception:
                store.close()
                raise
        self.controller.replace_cards(cards)
        self.store = store
        self.controller.set_project_root(store.root)
        self.assets = {asset.id: asset for asset in snapshot.assets}
        self.saver.reset(snapshot.revision, store.save)
        self._ui_restore_failed = False
        if previous is not None:
            previous.close()
        self._update_status()
        try:
            state = load_workspace_file(store.root)
            if state is not None:
                restore_workspace(self.controller, state)
        except (OSError, ValueError, TypeError, AttributeError) as error:
            self._ui_restore_failed = True
            self._show_error(error)

    def save_current(self) -> bool:
        self.controller.flush_edits()
        self.controller.media.wait_import()
        if self.store is None:
            folder = QFileDialog.getExistingDirectory(self.window, "Пустая папка нового проекта")
            if not folder:
                return False
            try:
                return self.create_project(Path(folder))
            except (OSError, ValueError) as error:
                self._show_error(error)
                return False
        return self.saver.save()

    def _confirm_changes(self) -> bool:
        self.controller.flush_edits()
        self.controller.media.wait_import()
        self.controller.maps.wait_import()
        self.mow_importer.wait_import()
        self.saver.wait_current()
        if not self._confirm_drafts():
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
        if not self._confirm_changes():
            return False
        try:
            self._save_ui_state()
        except OSError as error:
            self._show_error(error)
            return False
        self.saver.shutdown()
        self.controller.shutdown_features()
        self.mow_importer.shutdown()
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

    def _request_new(self):
        folder = QFileDialog.getExistingDirectory(self.window, "Пустая папка нового проекта")
        if not folder or not self._confirm_changes():
            return
        try:
            # Discard was explicit in the preceding dialog; retain the old data on disk.
            self.create_project(Path(folder), preserve_current=False, discard=True)
        except (OSError, ValueError) as error:
            self._show_error(error)

    def _request_open(self):
        folder = QFileDialog.getExistingDirectory(self.window, "Открыть папку проекта")
        if not folder or not self._confirm_changes():
            return
        try:
            self.open_project(Path(folder), discard=True)
        except (OSError, ValueError) as error:
            self._show_error(error)

    def _request_backup(self):
        if not self.save_current() or self.store is None:
            return
        dialog = QFileDialog(self.window, "Резервная копия")
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
        filename, _ = QFileDialog.getOpenFileName(
            self.window, "Восстановить копию", "", "LODANDSY backup (*.lodbackup)"
        )
        if not filename or not self._confirm_changes():
            return
        parent = QFileDialog.getExistingDirectory(self.window, "Где создать восстановленный проект")
        if not parent:
            return
        name, accepted = QInputDialog.getText(self.window, "Восстановление", "Имя новой папки:")
        if not accepted or not name.strip():
            return
        if any(char in name for char in '<>:"/\\|?*') or name in {".", ".."}:
            self._show_error("Недопустимое имя папки")
            return
        try:
            destination = Path(parent) / name.strip()
            restored = SQLiteProjectStore.restore(Path(filename), destination)
            restored.close()
            self.open_project(destination, discard=True)
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            self._show_error(error)
