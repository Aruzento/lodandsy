import json

import pytest

from lodandsy.application.workspace_state import (
    UI_STATE_NAME,
    capture_workspace,
    restore_workspace,
)

pytest_plugins = ["tests.project_fixture"]


def test_project_roundtrip_separates_selection_active_document_and_ui(project, tmp_path):
    controller, project = project
    root = tmp_path / "world"
    project.create_project(root)
    first = controller.create_card("First")
    second = controller.create_card("Second")
    editor = controller.open_card_editor(first.id).widget()
    controller.open_card_editor(second.id)
    editor.format_toolbar.scale.setValue(150)
    controller.cards_service.select_card(first.id)
    assert project.save_current()
    revision = project.store.load().revision
    project._save_ui_state()
    saved = json.loads((root / UI_STATE_NAME).read_text(encoding="utf-8"))
    for key in controller.window_manager.window_keys():
        controller.window_manager.close_window(key)
    restore_workspace(controller, saved)
    assert set(controller.card_views.editors) == {first.id, second.id}
    assert controller.cards_service.current_card_id == first.id
    assert controller.window_manager.active_window_key == f"card-editor:{second.id}"
    assert controller.card_views.editors[first.id].format_toolbar.scale.value() == 150
    assert project.store.load().revision == revision
    assert not project.saver.dirty


def test_missing_document_uses_safe_default_layout(project, tmp_path):
    controller, project = project
    project.create_project(tmp_path / "world")
    card = controller.create_card("Card")
    controller.open_card_editor(card.id)
    saved = capture_workspace(controller)
    saved["documents"].append("card-editor:missing")
    saved["layout"] = "aW52YWxpZA=="
    restore_workspace(controller, saved)
    assert controller.window_manager.find_window(f"card-editor:{card.id}") is not None


@pytest.mark.parametrize("data", [None, {"version": 100}, {"version": 1, "documents": 1}])
def test_invalid_layout_is_rejected_without_touching_world(project, data):
    controller, project = project
    card = controller.create_card("Kept")
    with pytest.raises(ValueError):
        restore_workspace(controller, data)
    assert controller.cards.get(card.id).title == "Kept"


def test_corrupt_layout_kept_before_replacement(project, tmp_path, monkeypatch):
    controller, project = project
    root = tmp_path / "world"
    project.create_project(root)
    controller.create_card("Kept")
    assert project.save_current()
    project.store.close()
    project.store = None
    (root / UI_STATE_NAME).write_text("corrupt", encoding="utf-8")
    errors = []
    monkeypatch.setattr(project, "_show_error", errors.append)
    project.open_project(root)
    assert errors and controller.cards.all()[0].title == "Kept"
    project._save_ui_state()
    assert next(root.glob(".ui-state-unreadable-*.json")).read_text() == "corrupt"
