from dataclasses import replace
from uuid import uuid4

import pytest

from lodandsy.application.card_payload_codec import decode_card, encode_card
from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.domain.card import Card, Portrait
from tests.test_card_images import image_file

pytest_plugins = ["tests.project_fixture"]


def test_typed_portrait_and_unknown_fields():
    portrait = Portrait(str(uuid4()), (0.1, 0.2, 0.5, 0.6))
    card = Card("A", portrait=portrait)
    version, source = encode_card(card)
    assert decode_card(card.title, card.id, None, version, source) == card
    with pytest.raises(ValueError):
        Portrait("../escape")
    with pytest.raises(ValueError):
        Card("A", portrait={"asset_id": portrait.asset_id})


def test_portrait_inline_replace_remove_reopen_backup(project, qtbot, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Person", card_type="character")
    assert card.portrait is None
    editor = app.open_card_editor(card.id).widget()
    source = image_file(tmp_path / "wide.png", 800, 200)
    app.card_images.portrait(editor, source)
    qtbot.waitUntil(lambda: not app.card_images.importing)
    portrait = app.cards.get(card.id).portrait
    assert portrait.asset_id in project.assets
    app.card_images.insert(editor, source, "Inline")
    qtbot.waitUntil(lambda: not app.card_images.importing)
    content = app.cards.get(card.id).content
    assert "<img" in content and len(project.assets) == 1
    editor.portrait_panel.changed.emit(replace(portrait, crop=(0.1, 0.2, 0.5, 0.6)))
    assert app.cards.get(card.id).portrait.crop == (0.1, 0.2, 0.5, 0.6)
    second = image_file(tmp_path / "second.png", 100, 100)
    app.card_images.portrait(editor, second)
    qtbot.waitUntil(lambda: not app.card_images.importing)
    updated = app.cards.get(card.id).portrait
    assert updated.asset_id != portrait.asset_id and len(project.assets) == 2
    assert updated.crop == (0, 0, 1, 1) and app.cards.get(card.id).content == content
    assert project.save_current()
    archive = tmp_path / "backup.zip"
    project.store.backup(archive)
    restored = SQLiteProjectStore.restore(archive, tmp_path / "restored")
    assert restored.load().cards[0].portrait == updated
    restored.close()
    project.open_project(tmp_path / "restored")
    editor = app.open_card_editor(card.id).widget()
    assert editor.portrait_panel.portrait == updated
    editor.portrait_panel.remove.click()
    assert app.cards.get(card.id).portrait is None
    assert app.cards.get(card.id).content == content and len(project.assets) == 2


def test_missing_portrait_never_changes_body_or_revision(project, qtbot, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Person", card_type="character")
    app.session.update_card(card.id, portrait=Portrait(str(uuid4())))
    before = app.cards.get(card.id)
    editor = app.open_card_editor(card.id).widget()
    editor.resize(720, 600)
    editor.show()
    editor.portrait_panel.refresh_image()
    assert "недоступен" in editor.portrait_panel.image.text()
    assert app.cards.get(card.id) == before
    assert project.save_current()
    assert project.store.load().cards[0] == before
    editor.portrait_panel.changed.emit(replace(before.portrait, asset_id=None))
    assert app.cards.get(card.id).portrait.asset_id is None


def test_import_survives_closed_editor_and_deleted_card(project, qtbot, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Person", card_type="character")
    editor = app.open_card_editor(card.id).widget()
    app.card_images.portrait(editor, image_file(tmp_path / "portrait.png"))
    app.window_manager.close_window(app.card_editor_window_key(card.id))
    qtbot.waitUntil(lambda: not app.card_images.importing)
    assert app.cards.get(card.id).portrait.asset_id in project.assets
    editor = app.open_card_editor(card.id).widget()
    app.card_images.portrait(editor, image_file(tmp_path / "removed.png", 70, 50))
    app.delete_card(card.id)
    qtbot.waitUntil(lambda: not app.card_images.importing)
    assert len(project.assets) == 1
