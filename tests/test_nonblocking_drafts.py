from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from lodandsy.application.rich_html import text_document
from lodandsy.application.save_coordinator import SaveState

pytest_plugins = ["tests.project_fixture"]


def test_invalid_card_and_table_drafts_do_not_block_valid_save_or_ack(project, tmp_path, qtbot):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Character", card_type="character")
    editor = app.open_card_editor(card.id).widget()
    app.cards_service.update_card_fields(card.id, {"hp": 15})
    editor.title_edit.setText("")
    editor.title_edit.finish()
    assert (
        app.cards_service.field_drafts[(card.id, "title")] == ""
        and app.cards.get(card.id).title == "Character"
    )
    table = app.tables_service.create_table("Table")
    view = app.tables.open_table(table.id).widget()
    from lodandsy.domain.table_document import ColumnDefinition, RowRecord

    col = ColumnDefinition("Number", "number")
    app.tables_service.edit_table(table.id, columns=(col,), rows=(RowRecord(),))
    assert not view.model.setData(view.model.index(0, 0), "bad")
    other = app.create_card("Saved even with invalid drafts")
    app.cards_service.update_card_fields(other.id, {"summary": "Valid"})
    assert project.save_current()
    assert (
        project.saver.state == SaveState.CLEAN
        and project.saver.revision == project.saver.saved_revision
    )
    loaded = project.store.load()
    assert next(c for c in loaded.cards if c.id == other.id).value("summary") == "Valid"
    assert next(c for c in loaded.cards if c.id == card.id).title == "Character"
    assert "Ошибочный ввод не сохранён" in project.status.text() and not project.saver.last_error

    def cancel():
        dialog = QApplication.activeModalWidget()
        dialog.button(QMessageBox.StandardButton.Cancel).click()

    QTimer.singleShot(0, cancel)
    assert not project._confirm_changes()
    assert project.draft_count == 2

    def discard():
        dialog = QApplication.activeModalWidget()
        next(b for b in dialog.buttons() if b.text() == "Отбросить ошибочный ввод").click()

    QTimer.singleShot(0, discard)
    assert project._confirm_changes() and project.draft_count == 0
    assert editor.title_edit.text() == "Character" and view.model.data(view.model.index(0, 0)) == ""


def test_rejected_total_rich_budget_is_a_visible_draft_without_premature_ack(
    project, tmp_path, qtbot
):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Large card")
    one = card.sections[0]
    two = app.cards_service.add_section(card.id, "Second")
    three = app.cards_service.add_section(card.id, "Third")
    app.cards_service.update_section(
        card.id,
        one.id,
        content=text_document("A" * 700).replace(
            "</body>", ("<p>" + "A" * 700 + "</p>") * 1999 + "</body>"
        ),
    )
    app.cards_service.update_section(
        card.id,
        two.id,
        content=text_document("B" * 700).replace(
            "</body>", ("<p>" + "B" * 700 + "</p>") * 1999 + "</body>"
        ),
    )
    editor = app.open_card_editor(card.id).widget()
    editor.select_section(three.id)
    document = editor.text_edit.document()
    previous = app.cards.get(card.id).section(three.id).content
    editor.text_edit.insertHtml(("<p>" + "C" * 700 + "</p>") * 2000)
    editor.flush_pending()
    assert (card.id, three.id) in app.cards_service.field_drafts
    assert app.cards.get(card.id).section(three.id).content == previous
    assert document.canonical_content == previous and document.isUndoAvailable()
    editor.select_section(two.id)
    editor.select_section(three.id)
    assert editor.text_edit.document() is document and len(editor.text_edit.toPlainText()) > 1400000
    assert project.save_current()
    assert (
        next(c for c in project.store.load().cards if c.id == card.id).section(three.id).content
        == previous
    )
    app.cards_service.discard_field_drafts(card.id)
    assert not app.cards_service.field_drafts and not editor.text_edit.toPlainText()
    assert document.canonical_content == previous
