import pytest
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QMessageBox

from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.application.save_coordinator import SaveState
from lodandsy.application.sqlite_project_store import ProjectError, SQLiteProjectStore
from lodandsy.ui.app_shell import AppShell


@pytest.fixture
def project(qtbot):
    window = AppShell()
    qtbot.addWidget(window, before_close_func=lambda widget: setattr(widget, "close_guard", None))
    controller = AppController(window)
    project = ProjectController(controller)
    yield controller, project
    window.close_guard = None
    project.saver.shutdown()
    if project.store:
        project.store.close()


def test_create_edit_autosave_and_reopen_restores_real_views(project, tmp_path, qtbot):
    controller, project = project
    folder = tmp_path / "Мир с пробелами"
    project.create_project(folder)
    project.saver._timer.setInterval(10)
    root = controller.create_card("Мир")
    child = controller.create_card("Город", root.id)
    editor = controller.open_card_editor(child.id).widget()
    editor.text_edit.insertPlainText("# Город\n\nИстория")
    qtbot.waitUntil(lambda: project.saver.state == SaveState.CLEAN)
    before = project.store.load()
    assert len(before.cards) == 2
    assert project.status.text().endswith("Сохранено")
    other = SQLiteProjectStore.create(tmp_path / "Другой")
    other.close()
    project.open_project(tmp_path / "Другой")
    assert controller.cards.all() == ()
    assert controller.card_editors == {}
    project.open_project(folder)
    assert controller.cards.all() == before.cards
    assert controller.window.tree_panel.tree_model.index_for_card(child.id).data() == "Город"
    reopened_editor = controller.open_card_editor(child.id).widget()
    assert reopened_editor.text_edit.toPlainText() == "# Город\n\nИстория"


def test_ctrl_s_action_uses_same_pipeline_and_safe_close_releases_lock(project, tmp_path):
    controller, project = project
    project.create_project(tmp_path / "world")
    card = controller.create_card("Card")
    controller.open_card_editor(card.id).widget().text_edit.insertPlainText("Saved")
    assert project.save_action.shortcut() == QKeySequence(QKeySequence.StandardKey.Save)
    project.save_action.trigger()
    assert not project.saver.dirty
    assert project.store.load().cards[0].content == "Saved"
    assert project.can_close()
    reopened = SQLiteProjectStore.open(tmp_path / "world")
    reopened.close()


def test_failed_write_is_visible_retry_works_and_close_can_be_cancelled(
    project, tmp_path, monkeypatch
):
    controller, project = project
    project.create_project(tmp_path / "world")
    persist = project.store.save
    def fail(snapshot):
        raise OSError("disk full")
    project.saver._persist = fail
    controller.create_card("Unwritten")
    assert not project.save_current()
    assert project.saver.state == SaveState.ERROR
    assert "disk full" in project.status.text()
    assert not project.retry.isHidden()
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.Cancel)
    assert not project.can_close()
    assert project.saver.dirty
    project.saver._persist = persist
    project.retry.click()
    assert not project.saver.dirty
    assert project.store.load().cards[0].title == "Unwritten"


def test_failed_new_project_does_not_clear_current_dirty_state(project, tmp_path, monkeypatch):
    controller, project = project
    project.create_project(tmp_path / "world")
    card = controller.create_card("Keep me")
    bad = tmp_path / "not-empty"
    bad.mkdir()
    (bad / "personal.txt").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(
        "lodandsy.application.project_controller.QFileDialog.getExistingDirectory",
        lambda *args: str(bad),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.Discard)
    errors = []
    monkeypatch.setattr(project, "_show_error", errors.append)
    project._request_new()
    assert errors and project.saver.dirty
    assert controller.cards.get(card.id).title == "Keep me"
    assert project.save_current()
    assert project.store.load().cards[0].id == card.id
    assert (bad / "personal.txt").read_text(encoding="utf-8") == "keep"


def test_open_requires_explicit_resolution_of_unsaved_changes(project, tmp_path):
    controller, project = project
    controller.create_card("Scratch")
    another = SQLiteProjectStore.create(tmp_path / "another")
    another.close()
    with pytest.raises(ProjectError, match="explicitly discard"):
        project.open_project(tmp_path / "another")
    assert controller.cards.all()[0].title == "Scratch"


def test_failed_open_keeps_current_project_and_documents(project, tmp_path):
    controller, project = project
    project.create_project(tmp_path / "world")
    card = controller.create_card("Kept")
    dock = controller.open_card_editor(card.id)
    assert project.save_current()
    with pytest.raises(ProjectError, match="No project"):
        project.open_project(tmp_path / "missing")
    assert controller.card_editors[card.id] is dock.widget()
    assert project.store.root == (tmp_path / "world").resolve()
