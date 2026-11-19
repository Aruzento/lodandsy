import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtGui import QImage, QTextDocument

from lodandsy.application.media_service import read_card_image
from lodandsy.application.rich_html import html_text, sanitize_html
from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.domain.card import EMPTY_DOCUMENT
from lodandsy.ui.card_editor import RichTextEdit
from lodandsy.ui.rich_document import RichDocument

pytest_plugins = ["tests.project_fixture"]


def image_file(path, width=20, height=10):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.red)
    assert image.save(str(path))
    return path


@pytest.mark.parametrize("extension", ["png", "jpg", "webp"])
def test_raster_formats_are_decoded_by_signature_and_thumbnails_are_bounded(tmp_path, extension):
    path = image_file(tmp_path / f"изображение.{extension}", 2100, 1200)
    image = read_card_image(path)
    assert image.width() == 1024 and image.height() < 1024
    fake = tmp_path / "renamed.png"
    fake.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    with pytest.raises(ValueError):
        read_card_image(fake)


def test_insert_deduplicate_undo_save_move_and_backup(project, qtbot, tmp_path):
    app, project = project
    project.create_project(tmp_path / "Мир")
    card = app.create_card("Card")
    editor = app.open_card_editor(card.id).widget()
    path = image_file(tmp_path / "оригинал.png")
    app.card_views.images.insert(editor, path, "Место [1]")
    qtbot.waitUntil(lambda: not app.media.importing)
    content = app.cards.get(card.id).content
    assert "<img" in content and "assets/" in content and len(project.assets) == 1
    editor.text_edit.undo()
    assert html_text(app.cards.get(card.id).content).strip() == ""
    assert len(project.assets) == 1
    editor.text_edit.redo()
    app.card_views.images.insert(editor, path, "Again")
    qtbot.waitUntil(lambda: not app.media.importing)
    assert len(project.assets) == 1
    assert project.save_current()
    backup = tmp_path / "world.lodbackup"
    project.store.backup(backup)
    restored = SQLiteProjectStore.restore(backup, tmp_path / "Восстановлен")
    restored.close()
    shutil.copytree(tmp_path / "Восстановлен", tmp_path / "Перенесён")
    project.open_project(tmp_path / "Перенесён")
    assert app.cards.get(card.id).content.count("assets/") == 2
    asset = next(iter(project.assets.values()))
    assert read_card_image(project.store.root / asset.path).width() == 20


def test_import_can_finish_after_editor_closed_but_not_deleted(project, qtbot, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Card")
    editor = app.open_card_editor(card.id).widget()
    app.card_views.images.insert(editor, image_file(tmp_path / "a.png"), "Alt")
    app.window_manager.close_window(app.card_editor_window_key(card.id))
    app.media.wait_import()
    assert "assets/" in app.cards.get(card.id).content
    assert project.save_current()
    editor = app.open_card_editor(card.id).widget()
    app.card_views.images.insert(editor, image_file(tmp_path / "b.png"), "Deleted")
    app.delete_card(card.id)
    app.media.wait_import()
    assert len(project.assets) == 1


def test_document_images_async_fit_missing_corrupt_and_content(project, qtbot, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Card")
    asset = project.store.import_asset(image_file(tmp_path / "wide.png", 2400, 800))
    project.assets[asset.id] = asset
    source = sanitize_html(f'<p><img src="{asset.path}" alt="wide"></p>')[0]
    app.cards_service.update_card(card.id, content=source)
    editor = app.open_card_editor(card.id).widget()
    editor.resize(420, 400)
    document = editor.text_edit.document()
    document.image(asset.path)
    qtbot.waitUntil(lambda: document.images.get(asset.path) is not None)
    fmt = document.begin().begin().fragment().charFormat()
    size = document._image_handler.intrinsicSize(document, 0, fmt)
    assert size.width() <= max(40, document.textWidth())
    assert app.cards.get(card.id).content == source
    assert project.save_current()
    root = project.store.root
    (root / asset.path).write_bytes(b"corrupt")
    project.create_project(tmp_path / "other", preserve_current=False)
    project.open_project(root)
    document = app.open_card_editor(card.id).widget().text_edit.document()
    document.image(asset.path)
    qtbot.waitUntil(lambda: document.images.get(asset.path) is not None)
    assert document.images[asset.path].isNull()
    assert app.cards.get(card.id).content == source


def test_paste_and_drop_image_share_import_signal_plain_text_stays_plain(qtbot, tmp_path):
    edit = RichTextEdit()
    qtbot.addWidget(edit)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(image_file(tmp_path / "a.png")))])
    with qtbot.waitSignal(edit.image_requested) as result:
        edit.insertFromMimeData(mime)
    assert isinstance(result.args[0], Path)
    mime = QMimeData()
    image = QImage(2, 2, QImage.Format.Format_RGB32)
    mime.setImageData(image)
    with qtbot.waitSignal(edit.image_requested):
        edit.insertFromMimeData(mime)
    mime = QMimeData()
    mime.setText("**source**")
    edit.insertFromMimeData(mime)
    assert edit.toPlainText() == "**source**"


def test_twenty_distinct_images_scroll_return_close_reopen_and_bounded_memory(
    project, qtbot, tmp_path
):
    from PySide6.QtGui import QTextCursor

    app, project = project
    app.window.show()
    project.create_project(tmp_path / "world")
    assets = []
    for i in range(20):
        image = QImage(1024, 1024, QImage.Format.Format_RGB32)
        image.fill(0xFF000000 | ((i + 1) * 7919))
        source = tmp_path / f"image{i}.png"
        assert image.save(str(source))
        assets.append(project.store.import_asset(source, known_assets=tuple(assets)))
    project.assets.update((a.id, a) for a in assets)
    card = app.create_card("Twenty distinct images")
    canonical = sanitize_html(
        "".join(f'<p>Image {i}</p><p><img src="{a.path}"></p>' for i, a in enumerate(assets))
    )[0]
    app.cards_service.update_card(card.id, content=canonical)
    editor = app.open_card_editor(card.id).widget()
    document = editor.text_edit.document()
    positions = {}
    block = document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.charFormat().isImageFormat():
                positions[fragment.charFormat().toImageFormat().name()] = fragment.position()
            it += 1
        block = block.next()
    assert len(positions) == 20
    for asset in [*assets, assets[0], assets[10]]:
        cursor = QTextCursor(document)
        cursor.setPosition(positions[asset.path])
        editor.text_edit.setTextCursor(cursor)
        editor.text_edit.ensureCursorVisible()
        editor.text_edit.viewport().update()
        qtbot.waitUntil(
            lambda: (image := document.image(asset.path)) is not None and not image.isNull(),
            timeout=10000,
        )
        assert document.image_budget <= 8 * 1024**2
        assert len(app.media._pending) <= 32
        assert sum(i.sizeInBytes() for i in app.media._cache.values()) <= 16 * 1024**2
    assert app.cards.get(card.id).content == canonical
    app.window_manager.close_window(app.card_editor_window_key(card.id))
    assert not document.images and document.image_budget == 0
    reopened = app.open_card_editor(card.id).widget().text_edit.document()
    assert reopened is document
    qtbot.waitUntil(lambda: (i := document.image(assets[0].path)) is not None and not i.isNull())
    assert project.save_current()


def test_symlink_image_cannot_escape_assets(qtbot, tmp_path):
    (tmp_path / "assets").mkdir()
    outside = image_file(tmp_path / "secret.png")
    link = tmp_path / "assets/link.png"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Windows account cannot create symlinks")
    document = RichDocument(EMPTY_DOCUMENT)
    document.configure_resources(tmp_path, lambda *a: pytest.fail("Escaped resource read"))
    assert document.image("assets/link.png").isNull()
    image = document.resource(QTextDocument.ResourceType.ImageResource, QUrl("assets/link.png"))
    assert image.width() == 1


def test_windows_junction_cannot_escape_assets_or_cache(qtbot, tmp_path):
    native = pytest.importorskip("_winapi")
    from lodandsy.application.map_pyramid import cache_directory

    root = tmp_path / "Мир"
    (root / "assets").mkdir(parents=True)
    outside = tmp_path / "Вне проекта"
    outside.mkdir()
    image_file(outside / "secret.png")
    native.CreateJunction(str(outside), str(root / "assets/link"))
    document = RichDocument(EMPTY_DOCUMENT)
    document.configure_resources(root, lambda *a: pytest.fail("Escaped resource read"))
    assert document.image("assets/link/secret.png").isNull()
    image = document.resource(
        QTextDocument.ResourceType.ImageResource, QUrl("assets/link/secret.png")
    )
    assert image.width() == 1
    native.CreateJunction(str(outside), str(root / ".lodandsy-cache"))
    with pytest.raises(ValueError, match="вне проекта"):
        cache_directory(root, "a" * 64)
