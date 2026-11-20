from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from lodandsy.application.project_history import ProjectHistory
from lodandsy.application.sqlite_project_store import ProjectError, SQLiteProjectStore
from lodandsy.ui.project_chooser import ProjectChooser

pytest_plugins = ["tests.project_fixture"]


def test_history_mru_unicode_dedup_remove_only_record(tmp_path):
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
    history.remove(a)
    assert (a / "personal.txt").read_text() == "keep"
    history.remember(tmp_path / "Moved", replaces=b)
    assert len(history.entries) == 1
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
    assert project.backup_action in controller.window.right_rail.settings_menu.actions()
    assert not hasattr(project, "mow_importer")


def test_welcome_error_cancel_then_success_through_controller(project, tmp_path):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    app, project = project
    store = SQLiteProjectStore.create(tmp_path / "Известный мир")
    store.close()
    project.history.remember(tmp_path / "Известный мир")
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
    assert project.store.root == (tmp_path / "Известный мир").resolve()
    assert app.window.isVisible()
