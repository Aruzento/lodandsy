import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from lodandsy.domain.card import EMPTY_DOCUMENT
from lodandsy.domain.card_schema import CARD_TYPES
from lodandsy.ui.card_creation_dialog import CardCreationDialog

pytest_plugins = ["tests.project_fixture"]


def test_type_registry_rejects_unknown_before_mutation(project, qtbot):
    app, _ = project
    assert set(CARD_TYPES) >= {"note", "article", "character", "location", "item"}
    assert "<body>" in EMPTY_DOCUMENT
    with pytest.raises(ValueError, match="Неизвестный"):
        app.create_card("Unknown", card_type="absent")
    assert app.cards.all() == ()


@pytest.mark.parametrize("card_type", ["note", "article", "character", "location", "item"])
def test_independent_type_sections_edit_save_reopen(project, tmp_path, card_type):
    app, project = project
    project.create_project(tmp_path / "one")
    first = app.create_card("First", card_type=card_type)
    second = app.create_card("Child", first.id, card_type=card_type)
    assert {s.id for s in first.sections}.isdisjoint(s.id for s in second.sections)
    assert first.content == second.content == EMPTY_DOCUMENT
    from lodandsy.application.rich_html import sanitize_html

    content = sanitize_html(
        EMPTY_DOCUMENT.replace(
            "</body>",
            f'<p><a href="lodandsy://entity/{second.id}">Связь</a>'
            '<img src="assets/missing.png" alt="Alt"></p></body>',
        )
    )[0]
    editor = app.open_card_editor(first.id).widget()
    assert "##" not in editor.text_edit.toPlainText()
    app.session.update_card(first.id, content=content)
    assert app.cards.get(second.id).content == second.content
    assert project.save_current()
    project.create_project(tmp_path / "two", preserve_current=False)
    project.open_project(tmp_path / "one")
    assert app.cards.get(first.id).content == content
    assert app.cards.get(second.id).parent_id == first.id
    assert app.cards.get(first.id).card_type == card_type


def test_creation_dialog_root_child_and_cancel(project, qtbot):
    app, _ = project
    panel = app.window.tree_panel

    def choose():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, CardCreationDialog)
        assert not dialog.ok.isEnabled()
        dialog.title_edit.setText("  Персонаж  ")
        dialog.card_type.setCurrentIndex(dialog.card_type.findData("character"))
        qtbot.mouseClick(dialog.ok, Qt.MouseButton.LeftButton)

    QTimer.singleShot(0, choose)
    panel.request_create_root()
    root = app.cards.all()[0]
    assert root.title == "Персонаж" and any(s.purpose == "inventory" for s in root.sections)
    panel.select_node("card:" + root.id)
    QTimer.singleShot(0, choose)
    panel.request_create_child()
    assert len(app.cards.child_ids(root.id)) == 1
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
    panel.request_create_root()
    assert len(app.cards.all()) == 2
