import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from lodandsy.application.rich_html import html_text
from lodandsy.domain.card_templates import CARD_TEMPLATES, card_template
from lodandsy.ui.card_creation_dialog import CardCreationDialog

pytest_plugins = ["tests.project_fixture"]


def test_registry_is_versioned_text_and_rejects_unknown_before_mutation(project, qtbot):
    app, _ = project
    assert {t.id for t in CARD_TEMPLATES} == {"empty", "article", "character", "location", "item"}
    assert all(t.version == 2 and isinstance(t.content, str) for t in CARD_TEMPLATES)
    assert "<body>" in card_template("empty").content
    with pytest.raises(ValueError, match="Неизвестный"):
        app.create_card("Unknown", template_id="absent")
    assert app.cards.all() == ()


@pytest.mark.parametrize("template", CARD_TEMPLATES)
def test_independent_template_copy_edit_save_reopen(project, tmp_path, template):
    app, project = project
    project.create_project(tmp_path / "one")
    first = app.create_card("First", template_id=template.id)
    second = app.create_card("Child", first.id, template_id=template.id)
    assert first.content == second.content == template.content
    from lodandsy.application.rich_html import sanitize_html

    content = sanitize_html(template.content.replace("</body>",
        f'<p><a href="lodandsy://entity/{second.id}">Связь</a>'
        '<img src="assets/missing.png" alt="Alt"></p></body>'))[0]
    editor = app.open_card_editor(first.id).widget()
    assert "##" not in editor.text_edit.toPlainText()
    app.session.update_card(first.id, content=content)
    assert app.cards.get(second.id).content == second.content
    assert project.save_current()
    project.create_project(tmp_path / "two", preserve_current=False)
    project.open_project(tmp_path / "one")
    assert app.cards.get(first.id).content == content
    assert app.cards.get(second.id).parent_id == first.id
    assert card_template(template.id).content == template.content


def test_creation_dialog_root_child_and_cancel(project, qtbot):
    app, _ = project
    panel = app.window.tree_panel
    def choose():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, CardCreationDialog)
        assert not dialog.ok.isEnabled()
        dialog.title_edit.setText("  Персонаж  ")
        dialog.template.setCurrentIndex(dialog.template.findData("character"))
        qtbot.mouseClick(dialog.ok, Qt.MouseButton.LeftButton)
    QTimer.singleShot(0, choose)
    panel.request_create_root()
    root = app.cards.all()[0]
    assert root.title == "Персонаж" and "Инвентарь" in html_text(root.content)
    panel.select_node("card:" + root.id)
    QTimer.singleShot(0, choose)
    panel.request_create_child()
    assert len(app.cards.child_ids(root.id)) == 1
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
    panel.request_create_root()
    assert len(app.cards.all()) == 2
