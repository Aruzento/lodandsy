import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QInputDialog

from lodandsy.application.markdown_commands import format_markdown, markdown_link, utf16_length
from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.application.workspace_state import capture_workspace, restore_workspace

pytest_plugins = ["tests.project_fixture"]


def apply(source, start, end, command):
    change = format_markdown(source, utf16_length(source[:start]),
                             utf16_length(source[:end]), command)
    if change is None:
        return source, None
    original = source.encode("utf-16-le")
    output = (original[:change.start * 2] + change.text.encode("utf-16-le")
              + original[change.end * 2:]).decode("utf-16-le")
    return output, change


@pytest.mark.parametrize("command,formatted", [
    ("bold", "**Текст**"), ("italic", "*Текст*"), ("strike", "~~Текст~~"),
    ("inline-code", "`Текст`"), ("h1", "# Текст"), ("h2", "## Текст"),
    ("h3", "### Текст"), ("quote", "> Текст"), ("bullet", "- Текст"),
    ("numbered", "1. Текст"), ("code-block", "```\nТекст\n```"),
])
def test_commands_toggle_selected_text_and_preserve_outside(command, formatted):
    original = "Начало\nТекст\nКонец  \t"
    result, _ = apply(original, 7, 12, command)
    assert result == f"Начало\n{formatted}\nКонец  \t"
    result, _ = apply(result, 7, 7 + len(formatted), command)
    assert result == original


@pytest.mark.parametrize("command,expected", [
    ("h1", "# абзац 😀"), ("quote", "> абзац 😀"), ("bold", "**абзац 😀**"),
])
def test_no_selection_uses_current_paragraph(command, expected):
    result, _ = apply("до\nабзац 😀\nпосле", 7, 7, command)
    assert result == f"до\n{expected}\nпосле"


def test_utf16_emoji_and_reverse_selection_do_not_shift_unrelated_text():
    source = "😀 до\nслово и 😀\nпосле"
    start, end = source.index("слово"), source.index(" и")
    result, change = apply(source, end, start, "bold")
    assert result == "😀 до\n**слово** и 😀\nпосле"
    assert change.anchor > change.position
    with pytest.raises(ValueError, match="Unicode"):
        format_markdown(source, 1, 2, "bold")


def test_multiline_lists_keep_blank_lines_and_trailing_selection_boundary():
    source = "один\n\nдва\nвне"
    result, _ = apply(source, 0, source.index("вне"), "numbered")
    assert result == "1. один\n\n2. два\nвне"
    restored, _ = apply(result, 0, result.index("вне"), "numbered")
    assert restored == source


def test_code_fences_and_spans_handle_embedded_backticks():
    source = "`внутри`"
    formatted, _ = apply(source, 0, len(source), "inline-code")
    # An existing complete span toggles off; a partial embedded run requires a longer fence.
    assert formatted == "внутри"
    formatted, _ = apply("a`b", 0, 3, "inline-code")
    assert formatted == "``a`b``"
    source = "a\n```python\nx\n```\nb"
    formatted, _ = apply(source, 0, len(source), "code-block")
    assert formatted.startswith("````\n") and formatted.endswith("\n````")
    assert apply(formatted, 0, len(formatted), "code-block")[0] == source


def test_separator_is_inserted_after_paragraph_without_deleting_selection():
    result, _ = apply("первый\nвторой", 1, 3, "rule")
    assert result == "первый\n\n---\n\nвторой"


def test_nested_italic_does_not_remove_bold_and_escaped_markers_are_not_removed():
    result, _ = apply("**слово**", 2, 7, "italic")
    assert result == "***слово***"
    assert apply(result, 3, 8, "italic")[0] == "**слово**"
    result, _ = apply(r"\**word**", 3, 7, "bold")
    assert result.startswith(r"\**") and result.endswith("**")


@pytest.mark.parametrize("command,expected", [
    ("h2", "## "), ("quote", "> "), ("bullet", "- "), ("numbered", "1. "),
])
def test_empty_paragraph_inserts_editable_prefix(command, expected):
    result, change = apply("", 0, 0, command)
    assert result == expected
    assert change.anchor == change.position == len(expected)


@pytest.mark.parametrize("target", ["file:///outside", "javascript:alert(1)", "ftp://host/file",
                                    "lodandsy://map/invalid", "https://host/\nvalue"])
def test_link_dialog_contract_rejects_blocked_schemes(target):
    with pytest.raises(ValueError):
        markdown_link("label", target)


def test_link_label_is_literal_and_target_parentheses_cannot_end_markdown_link():
    link = markdown_link("A [x] &copy;", "https://example.org/a(b) value")
    assert link == r"[A \[x\] \&copy\;](<https://example.org/a%28b%29%20value>)"


def test_toolbar_single_undo_preview_guard_and_reopen_keep_document_state(project, qtbot):
    app, project = project
    card = app.create_card("Card")
    app.session.update_card(card.id, content="😀 до\nслово\nпосле")
    editor = app.open_card_editor(card.id).widget()
    cursor = editor.text_edit.textCursor()
    cursor.setPosition(utf16_length("😀 до\n"))
    cursor.setPosition(utf16_length("😀 до\nслово"), QTextCursor.MoveMode.KeepAnchor)
    editor.text_edit.setTextCursor(cursor)
    toolbar = editor.format_toolbar
    toolbar.actions_by_name["bold"].trigger()
    assert app.cards.get(card.id).content == "😀 до\n**слово**\nпосле"
    editor.text_edit.undo()
    assert app.cards.get(card.id).content == "😀 до\nслово\nпосле"
    editor.text_edit.redo()
    assert app.cards.get(card.id).content == "😀 до\n**слово**\nпосле"
    before = app.cards.get(card.id).content
    editor.mode_combo.setCurrentIndex(1)
    assert not toolbar.actions_by_name["bold"].isEnabled()
    toolbar.apply("bold")
    assert app.cards.get(card.id).content == before
    editor.mode_combo.setCurrentIndex(2)
    toolbar.restore_preferences("serif", 140)
    app.window_manager.close_window(f"card-editor:{card.id}")
    reopened = app.open_card_editor(card.id).widget()
    assert reopened.format_toolbar.view_preset.currentData() == "serif"
    assert reopened.format_toolbar.scale.value() == 140
    assert reopened.mode_combo.currentIndex() == 2
    assert reopened.text_edit.toPlainText() == before
    reopened.text_edit.undo()
    assert app.cards.get(card.id).content == "😀 до\nслово\nпосле"


def test_view_preferences_persist_as_ui_without_world_revision_or_markup(project, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Card")
    app.session.update_card(card.id, content="# Титул\n\nТекст")
    editor = app.open_card_editor(card.id).widget()
    assert project.save_current()
    revision = project.store.load().revision
    editor.format_toolbar.restore_preferences("mono", 170)
    editor.mode_combo.setCurrentIndex(2)
    editor.render_preview()
    assert not project.saver.dirty
    assert project.store.load().revision == revision
    assert app.cards.get(card.id).content == "# Титул\n\nТекст"
    assert editor.preview.document().defaultFont().family() == "Consolas"
    data = capture_workspace(app)
    editor.format_toolbar.restore_preferences("sans", 100)
    restore_workspace(app, data)
    assert editor.format_toolbar.view_preset.currentData() == "mono"
    assert editor.format_toolbar.scale.value() == 170


def test_closed_document_view_preferences_survive_project_reopen_without_eager_documents(
    project, tmp_path
):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Card")
    editor = app.open_card_editor(card.id).widget()
    editor.format_toolbar.restore_preferences("serif", 150)
    app.window_manager.close_window(f"card-editor:{card.id}")
    assert project.save_current()
    other = SQLiteProjectStore.create(tmp_path / "other")
    other.close()
    project.open_project(tmp_path / "other")
    project.open_project(tmp_path / "world")
    assert app.card_document_states == {}
    editor = app.open_card_editor(card.id).widget()
    assert editor.format_toolbar.view_preset.currentData() == "serif"
    assert editor.format_toolbar.scale.value() == 150


def test_link_toolbar_inserts_source_in_one_undo_with_escaped_label(project, monkeypatch):
    app, project = project
    card = app.create_card("Card")
    editor = app.open_card_editor(card.id).widget()
    answers = iter([("[Лейбл]", True), ("https://example.org/a(b)", True)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: next(answers))
    editor.format_toolbar.insert_link()
    assert app.cards.get(card.id).content == r"[\[Лейбл\]](<https://example.org/a%28b%29>)"
    editor.text_edit.undo()
    assert app.cards.get(card.id).content == ""


def test_formatting_shortcuts_are_scoped_to_focused_document(project, qtbot):
    app, project = project
    app.window.show()
    a, b = app.create_card("A"), app.create_card("B")
    first = app.open_card_editor(a.id).widget()
    first.text_edit.insertPlainText("A")
    second = app.open_card_editor(b.id).widget()
    second.text_edit.insertPlainText("B")
    app.window.activateWindow()
    second.text_edit.setFocus()
    qtbot.waitUntil(app.window.isActiveWindow)
    qtbot.keyClick(second.text_edit, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    assert app.cards.get(a.id).content == "A"
    assert app.cards.get(b.id).content == "**B**"
    qtbot.keyClick(second.text_edit, Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier)
    assert second.format_toolbar.scale.value() == 110
    qtbot.keyClick(second.text_edit, Qt.Key.Key_2,
                  Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
    assert app.cards.get(b.id).content == "## **B**"
