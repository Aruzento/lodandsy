from PySide6.QtWidgets import QBoxLayout

from lodandsy.application.rich_html import html_text

pytest_plugins = ["tests.project_fixture"]


def test_one_field_model_from_header_and_inspector_and_invalid_draft(project, qtbot, tmp_path):
    app, project = project
    app.window.show()
    project.create_project(tmp_path / "world")
    card = app.create_card("Hero", template_id="character")
    editor = app.open_card_editor(card.id).widget()
    app.session.select_card(card.id)
    inspector = app.window.inspector_panel
    editor.title_edit.setText("Renamed")
    editor.title_edit.textEdited.emit("Renamed")
    assert app.session.entities.get(card.id).title == inspector.title_edit.text() == "Renamed"
    editor.fields_edited.emit({"hp": 15, "summary": "Guardian", "tags": ("port",)})
    assert inspector.field_form.controls["hp"].text() == "15"
    hp = inspector.field_form.controls["hp"]
    hp.setText("0")
    hp.editingFinished.emit()
    assert app.cards.get(card.id).value("hp") == 0
    assert float(editor.fields_form.controls["hp"].text()) == 0
    hp.setText("nan")
    hp.editingFinished.emit()
    assert app.cards.get(card.id).value("hp") == 0 and app.session.field_drafts
    assert not project.save_current()
    assert editor.validation_status.text()
    app.window_manager.close_window(app.card_editor_window_key(card.id))
    editor = app.open_card_editor(card.id).widget()
    assert editor.fields_form.controls["hp"].text() == "nan"
    editor.discard_drafts_requested.emit()
    assert not app.session.field_drafts and project.save_current()


def test_sections_preserve_independent_undo_selection_and_never_duplicate_description(
    project, tmp_path, qtbot
):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Hero", template_id="character")
    editor = app.open_card_editor(card.id).widget()
    editor.text_edit.insertPlainText("Description")
    description = editor.text_edit.document()
    editor.select_section("notes")
    editor.text_edit.insertPlainText("Notes")
    notes = editor.text_edit.document()
    assert notes is not description
    assert html_text(app.cards.get(card.id).value("description")).strip() == "Description"
    assert html_text(app.cards.get(card.id).value("notes")).strip() == "Notes"
    editor.text_edit.selectAll()
    editor.format_toolbar.apply("bold")
    cursor = editor.text_edit.textCursor()
    assert cursor.hasSelection()
    editor.select_section("description")
    assert editor.text_edit.toPlainText() == "Description"
    editor.select_section("notes")
    assert editor.text_edit.textCursor().hasSelection()
    app.window_manager.close_window(app.card_editor_window_key(card.id))
    editor = app.open_card_editor(card.id).widget()
    assert editor.current_section == "notes" and editor.text_edit.document() is notes
    editor.text_edit.undo()
    assert editor.text_edit.toPlainText() == "Notes"
    assert not editor.text_edit.textCursor().charFormat().font().bold()
    before = app.cards.get(card.id)
    editor.template_combo.setCurrentIndex(editor.template_combo.findData("empty"))
    after = app.cards.get(card.id)
    assert after.card_type == before.card_type and after.values == before.values
    assert project.save_current()
    loaded = project.store.load().cards[0]
    assert loaded == after and "description" not in dict(loaded.values)


def test_compact_header_responsive_layout_and_rich_fields_open_from_inspector(project, qtbot):
    from lodandsy.ui.card_editor import CardEditorWidget

    app, _ = project
    card = app.create_card("Hero", template_id="character")
    editor = app.open_card_editor(card.id).widget()
    preview = CardEditorWidget()
    qtbot.addWidget(preview)
    preview.set_canonical(card)
    preview.resize(360, 640)
    preview.show()
    qtbot.waitUntil(lambda: preview.hero_layout.direction() == QBoxLayout.Direction.TopToBottom)
    assert preview.minimumSizeHint().width() <= 400
    assert not preview.portrait_panel.caption.isVisible()
    assert editor.format_toolbar.format_menu.actions()
    app.session.select_card(card.id)
    app.window.inspector_panel.open_field_requested.emit(card.id, "notes")
    assert editor.current_section == "notes"
    assert len(app.card_editors) == 1
