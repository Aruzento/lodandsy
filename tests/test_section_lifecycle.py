import gc
from weakref import ref

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QImage
from shiboken6 import isValid

from lodandsy.domain.card import EMPTY_DOCUMENT, CardSection
from lodandsy.domain.card_collection import CardCollection

pytest_plugins = ["tests.project_fixture"]


def drain_deletions():
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()


def test_explicit_sections_and_default_content_have_one_unambiguous_constructor():
    cards = CardCollection()
    explicit = (CardSection("Свой раздел"),)
    assert cards.create("Explicit", sections=explicit).sections == explicit
    assert cards.create("Empty", sections=()).sections == ()
    assert cards.create("Default").content == EMPTY_DOCUMENT
    assert cards.create("Content", content=EMPTY_DOCUMENT).sections
    with pytest.raises(ValueError):
        cards.create("Ambiguous", sections=explicit, content=EMPTY_DOCUMENT)


def test_hundred_text_and_table_cycles_release_removed_resources_keep_live_undo(project, qtbot):
    app, _ = project
    card = app.create_card("Card")
    editor = app.open_card_editor(card.id).widget()
    editor.text_edit.insertPlainText("Live text")
    editor.flush_pending()
    live_document = editor.text_edit.document()
    state = app.card_views.documents[card.id]
    destroyed = []
    weak_documents, weak_views = [], []
    for i in range(100):
        section = app.cards_service.add_section(card.id, f"Text {i}")
        editor.select_section(section.id)
        document = editor.text_edit.document()
        document.destroyed.connect(lambda *args: destroyed.append(1))
        weak_documents.append(ref(document))
        state.section_preferences[section.id] = {"position": 12}
        editor.text_edit.insertPlainText("Pending removed input")
        app.cards_service.delete_section(card.id, section.id)
        assert not editor.pending_input
        table_section = app.cards_service.add_section(card.id, f"Table {i}", kind="table_ref")
        table = app.actions.section_table(card.id, table_section.id)
        editor.select_section(table_section.id)
        view = editor._embedded_tables[table_section.id]
        weak_views.append(ref(view))
        app.cards_service.delete_section(card.id, table_section.id)
        app.actions.delete_entity(table.id)
        drain_deletions()
        assert section.id not in state.sections and section.id not in state.section_preferences
        assert not editor._embedded_tables
        assert editor.text_edit.document() is live_document
    del document, view
    drain_deletions()
    assert len(destroyed) == 100
    assert all(item() is None or not isValid(item()) for item in weak_documents + weak_views)
    assert len(state.documents()) == 1 and not app.card_views._table_cards
    assert not app.tables_service.draft_count
    assert live_document.isUndoAvailable()
    editor.text_edit.undo()
    assert editor.text_edit.toPlainText() == ""


def test_deleted_primary_document_and_closed_section_state_are_freed(project, qtbot):
    app, _ = project
    card = app.create_card("Card")
    second = app.cards_service.add_section(card.id, "Second")
    editor = app.open_card_editor(card.id).widget()
    primary = editor.text_edit.document()
    editor.select_section(second.id)
    editor.text_edit.insertPlainText("Keep")
    editor.flush_pending()
    live = editor.text_edit.document()
    app.cards_service.delete_section(card.id, card.description_id)
    drain_deletions()
    assert not isValid(primary) and editor.text_edit.document() is live
    app.window_manager.close_window(app.card_editor_window_key(card.id))
    app.cards_service.delete_section(card.id, second.id)
    drain_deletions()
    state = app.card_views.documents[card.id]
    assert not state.documents() and not isValid(live)
    editor = app.open_card_editor(card.id).widget()
    assert editor.current_section is None
    app.window_manager.close_window(app.card_editor_window_key(card.id))


def test_pending_image_removal_does_not_publish_or_retain_deleted_section(project, qtbot, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Card")
    editor = app.open_card_editor(card.id).widget()
    section = app.cards_service.add_section(card.id, "Pending")
    editor.select_section(section.id)
    document = editor.text_edit.document()
    image = QImage(100, 50, QImage.Format.Format_RGB32)
    image.fill(0xFFBB2244)
    app.card_views.images.insert(editor, image, "Gone")
    app.cards_service.delete_section(card.id, section.id)
    drain_deletions()
    app.media.wait_import()
    assert not project.assets and not isValid(document)
    assert project.save_current() and not app.cards_service.field_drafts


def test_hidden_deleted_table_and_relink_release_only_old_view(project, qtbot):
    app, _ = project
    card = app.create_card("Character", card_type="character")
    section = next(s for s in card.sections if s.purpose == "inventory")
    table = app.actions.section_table(card.id, section.id)
    editor = app.open_card_editor(card.id).widget()
    editor.select_section(section.id)
    view = editor._embedded_tables[section.id]
    editor.select_section(card.description_id)
    app.actions.delete_entity(table.id)
    drain_deletions()
    assert section.id not in editor._embedded_tables and not isValid(view)
    table = app.actions.section_table(card.id, section.id, replace_link=True)
    editor.select_section(section.id)
    view = editor._embedded_tables[section.id]
    other = app.tables_service.create_table("Replacement", card.id)
    app.actions.section_table(card.id, section.id, existing_id=other.id, replace_link=True)
    drain_deletions()
    assert not isValid(view)
    assert editor._embedded_tables[section.id].property("table_id") == other.id
    assert app.tables_service.get_table(table.id)
