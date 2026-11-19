import hashlib
import json
from contextlib import closing

import pytest
from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtGui import QFont, QImage, QTextDocument

from lodandsy.application.rich_html import HEADER, html_text, sanitize_html, validate_html
from lodandsy.application.rich_text_codec import serialize_document
from lodandsy.application.sqlite_project_store import (
    ProjectError,
    connect_database,
)
from lodandsy.ui.card_editor import CardEditorWidget

pytest_plugins = ["tests.project_fixture"]


def test_new_card_visual_edit_format_undo_reopen_and_restart(project, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Статья", card_type="article")
    editor = app.open_card_editor(card.id).widget()
    assert isinstance(editor, CardEditorWidget)
    assert not editor.text_edit.isReadOnly()
    assert editor.section_bar.tabText(0) == "Описание"
    assert editor.text_edit.toPlainText() == ""
    assert "##" not in editor.text_edit.toPlainText()
    editor.text_edit.setPlainText("Текст 😀")
    editor.text_edit.selectAll()
    editor.format_toolbar.apply("bold")
    assert editor.text_edit.currentCharFormat().font().bold()
    editor.text_edit.undo()
    assert not editor.text_edit.currentCharFormat().font().bold()
    editor.text_edit.redo()
    editor.text_edit.selectAll()
    editor.format_toolbar.character(fontFamilies=["Georgia"], fontPointSize=18)
    editor.format_toolbar.align(1)
    editor.flush_pending()
    content = app.cards.get(card.id).content
    assert "Georgia" in content and "18pt" in content and "align" in content
    document = editor.text_edit.document()
    app.window_manager.close_window(f"card-editor:{card.id}")
    reopened = app.open_card_editor(card.id).widget()
    assert reopened.text_edit.document() is document
    assert document.isUndoAvailable()
    assert project.save_current()
    before = project.store.load()
    project.create_project(tmp_path / "other", preserve_current=False)
    project.open_project(tmp_path / "world")
    assert project.store.load() == before
    editor = app.open_card_editor(card.id).widget()
    editor.text_edit.selectAll()
    assert editor.text_edit.currentCharFormat().fontFamilies() == ["Georgia"]
    assert editor.text_edit.currentCharFormat().fontPointSize() == 18
    assert editor.text_edit.alignment() & Qt.AlignmentFlag.AlignHCenter


def test_visual_links_all_entities_broken_diagnostics_never_rewrite_document(project, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Source")
    target = app.create_card("Target")
    table = app.tables_service.create_table("Table")
    html = sanitize_html(
        f'<p><a href="lodandsy://entity/{target.id}">Independent</a></p>'
        f'<p><a href="lodandsy://entity/{table.id}">Table</a></p>'
    )[0]
    app.cards_service.update_card(card.id, content=html)
    editor = app.open_card_editor(card.id).widget()
    app.follow_link(QUrl(f"lodandsy://entity/{table.id}"), editor)
    assert app.window_manager.find_window(f"table:{table.id}") is not None
    app.follow_link(QUrl(f"lodandsy://entity/{target.id}"), editor)
    assert app.window_manager.find_window(f"card-editor:{target.id}") is not None
    app.rename_card(target.id, "Renamed")
    assert app.cards.get(card.id).content == html
    app.delete_card(target.id)
    before = app.cards.get(card.id).content
    revision = project.saver.revision
    editor.refresh_links()
    assert "Разорванная" in editor.link_status.text()
    assert app.cards.get(card.id).content == before and project.saver.revision == revision
    for url in (
        f"lodandsy://entity/{target.id}",
        "lodandsy://entity/not-a-uuid",
        "lodandsy://future/anything",
        "javascript:evil()",
        "file:///outside",
    ):
        app.follow_link(QUrl(url), editor)
        assert editor.link_status.text()
    assert app.card_views.editors[card.id] is editor


def test_view_scale_read_mode_resize_and_image_ready_do_not_dirty_world(project, tmp_path, qtbot):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Image")
    editor = app.open_card_editor(card.id).widget()
    source = tmp_path / "image.png"
    image = QImage(700, 350, QImage.Format.Format_RGB32)
    image.fill(0xFF338899)
    image.save(str(source))
    app.card_views.images.insert(editor, source, "Портрет [1]")
    qtbot.waitUntil(lambda: not app.media.importing)
    asset = next(iter(project.assets.values()))
    doc = editor.text_edit.document()
    doc.image(asset.path)
    qtbot.waitUntil(lambda: doc.images.get(asset.path) is not None)
    assert project.save_current()
    content, revision = app.cards.get(card.id).content, project.saver.revision
    before_height = doc.size().height()
    editor.format_toolbar.scale.setValue(200)
    assert doc.size().height() >= before_height
    assert serialize_document(doc) == content
    editor.resize(260, 400)
    qtbot.wait(40)
    assert app.cards.get(card.id).content == content
    assert project.saver.revision == revision
    assert "assets/" in content and "<img" in content and "Портрет [1]" in content
    app.window_manager.close_window(f"card-editor:{card.id}")
    again = app.open_card_editor(card.id).widget()
    assert again.text_edit.document() is doc
    assert again.format_toolbar.scale.value() == 200


def test_clipboard_offline_sentinel_and_sanitizer_limits(project, tmp_path):
    app, _ = project
    card = app.create_card("Safe")
    editor = app.open_card_editor(card.id).widget()
    data = QMimeData()
    data.setHtml(
        '<script>evil()</script><iframe src="https://bad.invalid"></iframe>'
        '<p onclick="evil()" style="background-image:url(file:///private)">Safe'
        '<img src="https://bad.invalid/image"><a href="javascript:evil()">Link</a></p>'
    )
    editor.text_edit.insertFromMimeData(data)
    editor.flush_pending()
    html = app.cards.get(card.id).content
    assert "Safe" in html and "Link" in html
    assert not any(value in html for value in ("evil()", "bad.invalid", "file:", "javascript:"))
    validate_html(html)
    assert sanitize_html(html)[0] == html
    document = editor.text_edit.document()
    for url in ("file:///outside", "https://bad.invalid/image", "assets/../outside"):
        resource = document.resource(QTextDocument.ResourceType.ImageResource, QUrl(url))
        assert isinstance(resource, QImage) and resource.width() == 1 and not resource.isNull()
    assert HEADER in html
    for invalid in ("x" * (2**21 + 1), "<div>" * 65 + "x" + "</div>" * 65, "<p>x</p>" * 20_001):
        with pytest.raises(ValueError):
            sanitize_html(invalid)


def test_unknown_rich_version_refuses_without_rewriting(project, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    app.create_card("Document")
    assert project.save_current()
    with closing(connect_database(project.store.path)) as connection, connection:
        encoded = json.loads(connection.execute("SELECT content FROM card_content").fetchone()[0])
        encoded["sections"][0]["kind"] = "future"
        connection.execute("UPDATE card_content SET content=?", (json.dumps(encoded),))
    digest = hashlib.sha256(project.store.path.read_bytes()).hexdigest()
    with pytest.raises(ProjectError):
        project.store.load()
    assert hashlib.sha256(project.store.path.read_bytes()).hexdigest() == digest


def test_visual_shortcuts_affect_only_focused_card(project, qtbot):
    app, _ = project
    app.window.show()
    a, b = app.create_card("A"), app.create_card("B")
    first, second = app.open_card_editor(a.id).widget(), app.open_card_editor(b.id).widget()
    first.text_edit.setPlainText("First")
    second.text_edit.setPlainText("Second")
    second.text_edit.selectAll()
    app.window.activateWindow()
    second.text_edit.setFocus()
    qtbot.waitUntil(app.window.isActiveWindow)
    qtbot.keyClick(second.text_edit, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    assert second.text_edit.currentCharFormat().fontWeight() == QFont.Weight.Bold
    first.text_edit.selectAll()
    assert not first.text_edit.currentCharFormat().font().bold()
    second.flush_pending()
    assert "Second" in html_text(app.cards.get(b.id).content)


@pytest.mark.parametrize(
    "fragment",
    [
        "<h1>Заголовок 😀</h1><p><b>Жирный</b> и <i>курсив</i></p>",
        "<ul><li>Один<ul><li>Вложенный</li></ul></li><li>Два</li></ul>",
        "<ol><li>Первый</li><li>Второй</li></ol><blockquote>Цитата</blockquote>",
        "<pre>строка 1\n  отступ\nстрока 3</pre>",
        "<table><tr><th>Имя</th><th>Число</th></tr><tr><td>Ёж</td><td>0</td></tr></table>",
        '<p><span style="font-family:Georgia;font-size:18pt;color:#ceb075;'
        'text-decoration:underline line-through">Оформление</span></p>',
    ],
)
def test_current_document_semantic_roundtrip(project, tmp_path, fragment):
    app, project = project
    html = sanitize_html(fragment)[0]
    card = app.create_card("Corpus")
    app.cards_service.update_card(card.id, content=html)
    editor = app.open_card_editor(card.id).widget()
    document = editor.text_edit.document()
    before = document.toPlainText()
    encoded = serialize_document(document)
    clone = type(document)(encoded)
    assert clone.toPlainText() == before
    block_a, block_b = document.begin(), clone.begin()
    while block_a.isValid() and block_b.isValid():
        assert block_a.blockFormat().headingLevel() == block_b.blockFormat().headingLevel()
        list_a, list_b = block_a.textList(), block_b.textList()
        assert bool(list_a) == bool(list_b)
        if list_a:
            assert list_a.format().style() == list_b.format().style()
            assert list_a.format().indent() == list_b.format().indent()
        block_a, block_b = block_a.next(), block_b.next()
    assert not block_a.isValid() and not block_b.isValid()
    clone.deleteLater()


def test_only_entity_uri_and_http_activation_are_supported(project, monkeypatch):
    from PySide6.QtGui import QDesktopServices

    app, _ = project
    card = app.create_card("Target")
    editor = app.open_card_editor(card.id).widget()
    calls = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl", lambda url: calls.append(url.toString()) or True
    )
    html = sanitize_html('<p><a href="https://example.org">External</a></p>')[0]
    app.cards_service.update_card(card.id, content=html)
    editor.refresh_links()
    assert not calls
    app.follow_link(QUrl(f"lodandsy://card/{card.id}"), editor)
    assert editor.link_status.text() and not calls
    app.follow_link(QUrl("https://example.org"), editor)
    assert calls == ["https://example.org"]


def test_source_formats_and_archive_schema_are_absent(project, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    app.create_card("Only visual")
    assert project.save_current()
    with closing(connect_database(project.store.path)) as connection, connection:
        tables = {
            r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "card_migration_archive" not in tables
        connection.execute("UPDATE card_content SET payload_version=1")
    digest = hashlib.sha256(project.store.path.read_bytes()).hexdigest()
    with pytest.raises(ProjectError, match="Unsupported Card payload"):
        project.store.load()
    assert hashlib.sha256(project.store.path.read_bytes()).hexdigest() == digest
