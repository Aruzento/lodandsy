import errno
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier

import pytest
from PySide6.QtCore import QSettings, QStandardPaths, Qt, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from lodandsy.application.project_catalogue import ProjectCatalogue
from lodandsy.application.project_history import ProjectHistory
from lodandsy.application.sqlite_project_store import (
    SCHEMA_VERSION,
    ProjectError,
    SQLiteProjectStore,
    connect_database,
)
from lodandsy.ui.project_chooser import ProjectChooser
from lodandsy.ui.project_name_dialog import ProjectNameDialog

pytest_plugins = ["tests.project_fixture"]


def test_history_mru_unicode_dedup_and_opening_timestamp(tmp_path):
    settings = QSettings(str(tmp_path / "user.ini"), QSettings.Format.IniFormat)
    history = ProjectHistory(settings)
    a, b = tmp_path / "Мир А", tmp_path / "Мир Б"
    a.mkdir()
    (a / "personal.txt").write_text("keep")
    history.remember(a)
    history.remember(b)
    history.remember(a / ".." / a.name)
    assert [e["path"] for e in history.entries] == [str(a), str(b)]
    assert ProjectHistory(settings).entries == history.entries
    assert all(entry["opened_at"] for entry in history.entries)
    assert history.last_directory == str(tmp_path)


def test_catalogue_does_not_probe_missing_paths(qtbot, tmp_path, monkeypatch):
    entries = ({"title": "Missing", "path": str(tmp_path / "Missing")},)
    monkeypatch.setattr(Path, "exists", lambda _: pytest.fail("No startup filesystem probes"))
    dialog = ProjectChooser(entries, welcome=True)
    qtbot.addWidget(dialog)
    assert dialog.projects.currentRow() == 0
    with qtbot.waitSignal(dialog.open_requested) as signal:
        dialog.open_button.click()
    assert signal.args == [entries[0]["path"]]


def test_only_successful_open_create_are_recorded_and_settings_are_on_rail(project, tmp_path):
    controller, project = project
    assert not project.backup_action.isEnabled() and not project.restore_action.isEnabled()
    project.create_project(tmp_path / "А")
    before = project.history.entries
    with pytest.raises(ProjectError):
        project.open_project(tmp_path / "missing")
    assert project.history.entries == before
    locked = SQLiteProjectStore.create(tmp_path / "Locked")
    try:
        with pytest.raises(ProjectError):
            project.open_project(locked.root)
        assert project.history.entries == before
    finally:
        locked.close()
    project.open_project(tmp_path / "Locked")
    assert project.history.entries[0]["title"] == "Locked"
    menu = controller.window.menuBar().actions()[0].menu()
    assert project.backup_action not in menu.actions()
    assert controller.window.right_rail.settings_button.menu() is None
    assert not hasattr(project, "mow_importer")


def test_welcome_error_cancel_then_success_through_controller(project, tmp_path):
    app, project = project
    project.catalogue = ProjectCatalogue(lambda: tmp_path / "Documents")
    with project.catalogue.reserve("Известный мир") as destination:
        SQLiteProjectStore.create_new(destination).close()
    before = project.history.entries

    def cancel():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, ProjectChooser)
        assert dialog.parentWidget() is None
        assert project.store is None and not app.window.isVisible()
        dialog.open_requested.emit(str(tmp_path / "missing"))
        assert project.store is None and dialog.error.text()
        dialog.reject()

    QTimer.singleShot(0, cancel)
    assert not project.choose_project(welcome=True)
    assert project.history.entries == before

    def accept():
        dialog = QApplication.activeModalWidget()
        assert dialog.projects.currentRow() == 0
        dialog.open_button.click()

    QTimer.singleShot(0, accept)
    assert project.choose_project(welcome=True)
    assert project.store.root == project.catalogue.root / "Известный мир"
    assert app.window.isVisible()


def test_name_dialog_uses_redirected_documents_for_new_and_restore(
    project, qtbot, tmp_path, monkeypatch,
):
    app, project = project
    documents = tmp_path / "Перенаправленные документы"

    def documents_location(location):
        assert location == QStandardPaths.StandardLocation.DocumentsLocation
        return str(documents)

    monkeypatch.setattr(QStandardPaths, "writableLocation", documents_location)
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", lambda *a: pytest.fail("Папку выбирать не нужно")
    )
    assert project.catalogue.entries(()) == ()
    assert not documents.exists()

    def enter_name():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, ProjectNameDialog)
        dialog.name.setText("AUX.txt")
        assert not dialog.confirm.isEnabled()
        dialog.name.setText("Этар и Окрестности ✨")
        assert str(project.catalogue.root / dialog.name.text()) == dialog.path.text()
        qtbot.keyClick(dialog.name, Qt.Key.Key_Return)

    QTimer.singleShot(0, enter_name)
    assert project._request_new()
    path = documents / "LODANDSY" / "project" / "Этар и Окрестности ✨"
    assert project.store.root == path.resolve()
    card = app.create_card("Заметка")
    assert project.save_current()
    backup = tmp_path / "Этар — копия.lodbackup"
    project.store.backup(backup)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(backup), ""))

    def restore_name():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, ProjectNameDialog)
        assert dialog.name.text() == backup.stem
        dialog.name.setText(path.name.upper())
        dialog.confirm.click()
        assert "уже существует" in dialog.error.text()
        dialog.name.setText("Восстановленный мир")
        dialog.confirm.click()

    QTimer.singleShot(0, restore_name)
    project._request_restore()
    assert project.store.root == path.parent / "Восстановленный мир"
    assert project.store.load().cards[0].id == card.id
    assert {entry["title"] for entry in project.catalogue.entries(())} == {
        path.name, "Восстановленный мир",
    }


@pytest.mark.parametrize(
    "name", ["", "  ", ".", "..", "../Мир", "a\\b", "C:World", "name.", "name ",
             "AUX.txt", "CON", "COM¹", "LPT9", "🚩" * 250, "a\x00b", ".lodandsy-restore-secret"],
)
def test_managed_project_name_validation(tmp_path, name):
    catalogue = ProjectCatalogue(lambda: tmp_path)
    with pytest.raises(ProjectError):
        catalogue.destination(name)
    assert not catalogue.root.exists()


def test_catalogue_lists_valid_worlds_and_diagnoses_damage_without_writes(tmp_path):
    catalogue = ProjectCatalogue(lambda: tmp_path)
    root = catalogue.root
    world = root / "Валидный мир"
    SQLiteProjectStore.create_new(world).close()
    future = SQLiteProjectStore.create_new(root / "Будущий мир")
    future.close()
    with closing(connect_database(future.path)) as conn, conn:
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
    (future.root / ".lodandsy.lock").unlink()
    invalid = root / "Повреждённый"
    invalid.mkdir()
    (invalid / future.path.name).write_bytes(b"broken")
    (root / "Обычная папка").mkdir()
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    entries = {entry["title"]: entry for entry in catalogue.entries(())}
    assert set(entries) == {world.name, future.root.name, invalid.name}
    assert not entries[world.name]["error"]
    assert str(SCHEMA_VERSION + 1) in entries[future.root.name]["error"]
    assert entries[invalid.name]["error"]
    with pytest.raises(ProjectError, match="Unsupported project schema"):
        SQLiteProjectStore.open(future.root)
    assert before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_concurrent_managed_create_has_one_winner_even_with_case_variants(tmp_path):
    catalogue = ProjectCatalogue(lambda: tmp_path)
    barrier = Barrier(2)

    def create(name):
        barrier.wait(timeout=5)
        try:
            with catalogue.reserve(name) as path:
                SQLiteProjectStore.create_new(path).close()
        except (OSError, ProjectError):
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create, ["Этар", "ЭТАР"])) == [False, True]
    assert sum(not e["error"] for e in catalogue.entries(())) == 1


def test_separate_process_cannot_open_world_until_writer_releases_lock(tmp_path):
    script = """
from pathlib import Path
from sys import argv
from lodandsy.application.sqlite_project_store import ProjectError, SQLiteProjectStore
try:
    store = SQLiteProjectStore.open(Path(argv[1]))
except ProjectError as error:
    assert "already open" in str(error)
    raise SystemExit(7)
store.close()
"""
    folder = tmp_path / "Локальная игра"
    command = [sys.executable, "-c", script, str(folder)]
    with closing(SQLiteProjectStore.create_new(folder)):
        locked = subprocess.run(command, capture_output=True, check=False, timeout=15)
        assert locked.returncode == 7, locked.stderr
    assert subprocess.run(command, check=False, timeout=15).returncode == 0


def test_failed_create_and_restore_keep_current_world_and_destination_clean(
    project, tmp_path, monkeypatch,
):
    app, project = project
    project.catalogue = ProjectCatalogue(lambda: tmp_path / "Documents")
    assert project.create_project("Текущий")
    root = project.catalogue.root
    current = project.store
    card = app.create_card("Останется в текущем мире")
    assert project.save_current()
    backup = tmp_path / "backup.lodbackup"
    current.backup(backup)
    with monkeypatch.context() as patch:
        create = SQLiteProjectStore.create

        def disk_full(folder, **kwargs):
            create(folder, **kwargs).close()
            raise OSError(errno.ENOSPC, "disk full")

        patch.setattr(SQLiteProjectStore, "create", disk_full)
        with pytest.raises(OSError, match="disk full"):
            project.create_project("Не сохранилось")
    with monkeypatch.context() as patch:
        patch.setattr("shutil.disk_usage", lambda _: type("Usage", (), {"free": 0})())
        with pytest.raises(ProjectError, match="Недостаточно"):
            project.restore_project(backup, "Не восстановилось")
    assert project.store is current
    assert current.load().cards[0].id == card.id
    assert [p.name for p in root.iterdir() if p.is_dir()] == ["Текущий"]


def test_denied_documents_write_reports_error_without_creating_world(tmp_path, monkeypatch):
    catalogue = ProjectCatalogue(lambda: tmp_path / "Documents")
    mkdir = Path.mkdir

    def deny(path, *args, **kwargs):
        if path == catalogue.root.parent:
            raise PermissionError(errno.EACCES, "access denied", str(path))
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", deny)
    with pytest.raises(PermissionError, match="access denied"), catalogue.reserve("Этар"):
        pytest.fail("Нельзя выделить путь при отсутствии прав записи")
    assert not catalogue.root.exists()


def test_failed_open_after_discard_confirmation_preserves_current_draft(project, tmp_path):
    app, project = project
    assert project.create_project(tmp_path / "Текущий")
    card = app.create_card("Сохранённое имя")
    editor = app.open_card_editor(card.id).widget()
    editor.title_edit.setText("")
    editor.title_edit.finish()
    assert project.save_current()

    def refuse_switch_target():
        chooser = QApplication.activeModalWidget()
        QTimer.singleShot(0, confirm_discard)
        chooser.open_requested.emit(str(tmp_path / "missing"))
        assert chooser.error.text()
        assert editor.title_edit.text() == ""
        chooser.reject()

    def confirm_discard():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        next(b for b in dialog.buttons() if b.text() == "Отбросить ошибочный ввод").click()

    project.catalogue = ProjectCatalogue(lambda: tmp_path / "Docs")
    QTimer.singleShot(0, refuse_switch_target)
    assert not project.choose_project()
    assert project.draft_count == 1
    assert project.store.root.name == "Текущий"
