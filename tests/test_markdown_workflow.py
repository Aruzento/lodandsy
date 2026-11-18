from uuid import uuid4

import pytest
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QImage, QTextDocument

from lodandsy.application.app_controller import AppController
from lodandsy.application.markdown_links import (
    card_link,
    internal_card_id,
    preview_markdown,
    resolve_asset_image,
)
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.card_editor import MarkdownBrowser


def make_controller(qtbot):
    window = AppShell()
    qtbot.addWidget(window)
    return AppController(window)


def test_markdown_modes_never_rewrite_source_or_reset_undo(qtbot):
    controller = make_controller(qtbot)
    card = controller.create_card("Source")
    editor = controller.open_card_editor(card.id).widget()
    source = "# Заголовок\n\n**Текст**  \n\n- A\n- B\n"
    editor.text_edit.insertPlainText(source)
    for mode in [1, 2, 0, 2]:
        editor.mode_combo.setCurrentIndex(mode)
        assert controller.cards.get(card.id).content == source
        assert editor.text_edit.toPlainText() == source
    assert "Заголовок" in editor.preview.toPlainText()
    editor.text_edit.undo()
    assert controller.cards.get(card.id).content == ""


def test_links_open_target_without_retargeting_source_and_rename_does_not_rewrite_label(qtbot):
    controller = make_controller(qtbot)
    a, b = controller.create_card("A"), controller.create_card("B")
    source = controller.open_card_editor(a.id).widget()
    text = f"[Моя подпись](lodandsy://card/{b.id})"
    source.text_edit.insertPlainText(text)
    source.mode_combo.setCurrentIndex(2)
    source.preview.anchorClicked.emit(QUrl(f"lodandsy://card/{b.id}"))
    assert set(controller.card_editors) == {a.id, b.id}
    assert source.card_id == a.id
    controller.rename_card(b.id, "Новое имя")
    assert controller.cards.get(a.id).content == text
    assert "Моя подпись" in source.preview.toPlainText()
    existing = controller.card_editors[b.id]
    source.preview.anchorClicked.emit(QUrl(f"lodandsy://card/{b.id}"))
    assert controller.card_editors[b.id] is existing
    controller.delete_card(b.id)
    assert source.card_id == a.id and a.id in controller.card_editors
    assert "Разорванная" in source.link_status.text()
    source.preview.anchorClicked.emit(QUrl(f"lodandsy://card/{b.id}"))
    assert "Разорванная" in source.link_status.text()
    assert controller.cards.get(a.id).content == text


@pytest.mark.parametrize("url", [
    "lodandsy://card/not-a-uuid", f"lodandsy://map/{uuid4()}",
    "file:///C:/secret.txt", "javascript:alert(1)", "data:text/html,bad", "ftp://example.com/a",
])
def test_invalid_internal_links_and_unapproved_schemes_do_not_reach_os(qtbot, monkeypatch, url):
    controller = make_controller(qtbot)
    card = controller.create_card("A")
    editor = controller.open_card_editor(card.id).widget()
    opened = []
    monkeypatch.setattr(
        "lodandsy.application.app_controller.QDesktopServices.openUrl", opened.append
    )
    controller.follow_link(QUrl(url), editor)
    assert opened == []
    assert editor.link_status.text()
    assert controller.card_editors[card.id] is editor


def test_http_is_opened_only_on_activation_not_on_render(qtbot, monkeypatch):
    controller = make_controller(qtbot)
    card = controller.create_card("A")
    editor = controller.open_card_editor(card.id).widget()
    opened = []
    def open_url(url):
        opened.append(url.toString())
        return True
    monkeypatch.setattr("lodandsy.application.app_controller.QDesktopServices.openUrl", open_url)
    editor.text_edit.insertPlainText("[Web](https://example.com/path)")
    editor.mode_combo.setCurrentIndex(2)
    assert opened == []
    editor.preview.anchorClicked.emit(QUrl("https://example.com/path"))
    assert opened == ["https://example.com/path"]


def test_copy_link_escapes_title_and_uses_document_id_not_selection(qtbot, monkeypatch):
    controller = make_controller(qtbot)
    title = r"A [B] *C* &copy; `code` \\"
    a, b = controller.create_card(title), controller.create_card("Other")
    editor = controller.open_card_editor(a.id).widget()
    controller.session.select_card(b.id)
    copied = []
    monkeypatch.setattr(
        "lodandsy.application.app_controller.copy_text", copied.append,
    )
    editor.copy_link_button.click()
    assert copied == [card_link(a.id, title)]
    assert internal_card_id(copied[0].split("](")[-1][:-1]) == a.id
    document = QTextDocument()
    document.setMarkdown(copied[0])
    assert document.toPlainText() == title


def test_preview_allows_only_project_assets_and_replaces_remote_images(qtbot, tmp_path):
    root = tmp_path / "world"
    (root / "assets").mkdir(parents=True)
    image = QImage(8, 8, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.red)
    assert image.save(str(root / "assets/local.png"))
    assert image.save(str(tmp_path / "outside.png"))
    browser = MarkdownBrowser()
    qtbot.addWidget(browser)
    browser.project_root = root
    browser.render_markdown(
        "![remote](https://example.com/never-fetch.png)\n\n![local](assets/local.png)\n\n"
        f"![blocked]({(tmp_path / 'outside.png').as_uri()})"
    )
    assert "Удалённое изображение заблокировано" in browser.toPlainText()
    assert "Изображение недоступно" in browser.toPlainText()
    resource = browser.loadResource(
        QTextDocument.ResourceType.ImageResource, QUrl("assets/local.png")
    )
    assert isinstance(resource, QImage) and not resource.isNull()
    blocked = browser.document().resource(
        QTextDocument.ResourceType.ImageResource, QUrl((tmp_path / "outside.png").as_uri())
    )
    # The valid transparent sentinel blocks Qt's native local-file fallback.
    assert isinstance(blocked, QImage)
    assert blocked.width() == blocked.height() == 1
    assert blocked.pixelColor(0, 0).alpha() == 0


@pytest.mark.parametrize("path", [
    "assets/../../outside.png", "assets/%2e%2e/outside.png", "assets/%5c..%5coutside.png",
    "//server/assets/image.png", "file:///C:/assets/image.png", "/assets/image.png",
    "https://example.com/assets/a.png", "assets/a.png?query", "assets/a.png#fragment",
])
def test_asset_path_policy_rejects_escapes_and_uri_schemes(tmp_path, path):
    assert resolve_asset_image(tmp_path, path) is None


def test_search_matches_title_and_content_and_opens_independent_document(qtbot):
    controller = make_controller(qtbot)
    a, b = controller.create_card("A"), controller.create_card("Город")
    controller.session.update_card(b.id, content="Скрытая ПОДСКАЗКА")
    controller.open_card_editor(a.id)
    controller.open_search()
    search = controller._search_dialog
    search.query.setText("подсказка")
    qtbot.waitUntil(lambda: search.results.count() == 1)
    search.results.itemActivated.emit(search.results.item(0))
    assert set(controller.card_editors) == {a.id, b.id}
    assert controller.card_editors[a.id].card_id == a.id


def test_preview_resource_cache_does_not_leak_between_projects(qtbot, tmp_path):
    browser = MarkdownBrowser()
    qtbot.addWidget(browser)
    for name, color in [("one", Qt.GlobalColor.red), ("two", Qt.GlobalColor.blue)]:
        root = tmp_path / name
        (root / "assets").mkdir(parents=True)
        image = QImage(2, 2, QImage.Format.Format_ARGB32)
        image.fill(color)
        assert image.save(str(root / "assets/same.png"))
        browser.project_root = root
        browser.render_markdown("![same](assets/same.png)")
        loaded = browser.document().resource(
            QTextDocument.ResourceType.ImageResource, QUrl("assets/same.png")
        )
        assert isinstance(loaded, QImage)
        assert loaded.pixelColor(0, 0) == image.pixelColor(0, 0)


def test_html_image_and_stylesheet_resources_cannot_escape_project(qtbot, tmp_path):
    browser = MarkdownBrowser()
    qtbot.addWidget(browser)
    browser.project_root = tmp_path
    source = '<img src="https://example.com/no-network.png">'
    browser.render_markdown(source)
    assert "Удалённое изображение заблокировано" in browser.toPlainText()
    blocked = browser.document().resource(
        QTextDocument.ResourceType.StyleSheetResource, QUrl("file:///C:/secret.css")
    )
    assert bytes(blocked) == b"blocked-resource"


def test_preview_image_policy_preserves_html_in_code_examples():
    code = '<img src="https://example.com/code.png">'
    for source in [f"`{code}`", f"```html\n{code}\n```", f"    {code}"]:
        assert preview_markdown(source) == source


def test_svg_is_not_decoded_even_if_renamed_as_png(qtbot, tmp_path):
    (tmp_path / "assets").mkdir()
    path = tmp_path / "assets/looks-like-raster.png"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8">'
        '<image href="file:///C:/outside.png" width="8" height="8"/></svg>',
        encoding="utf-8",
    )
    browser = MarkdownBrowser()
    qtbot.addWidget(browser)
    browser.project_root = tmp_path
    browser.render_markdown("![vector](assets/looks-like-raster.png)")
    assert "Изображение недоступно" in browser.toPlainText()
    assert browser._image("assets/looks-like-raster.png") is None
