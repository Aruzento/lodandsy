from lodandsy.application.card_editor_binding import CardEditorBinding
from lodandsy.application.cards_service import CardsService
from lodandsy.application.rich_html import html_text, text_document
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.card_editor import CardEditorWidget


def test_editor_binding_updates_card_content(qtbot):
    cards = CardCollection()
    card = cards.create("Card")
    cards.update_content(card.id, text_document("Original"))
    session = CardsService(cards)
    editor = CardEditorWidget()
    qtbot.addWidget(editor)
    binding = CardEditorBinding(session, editor, card.id)
    assert editor.text_edit.toPlainText() == "Original"
    editor.text_edit.setPlainText("Changed")
    editor.flush_pending()
    assert html_text(cards.get(card.id).content).strip() == "Changed"
    assert binding.session is session


def test_selection_does_not_retarget_fixed_document(qtbot):
    cards = CardCollection()
    first, second = cards.create("First"), cards.create("Second")
    session = CardsService(cards)
    editor = CardEditorWidget()
    qtbot.addWidget(editor)
    binding = CardEditorBinding(session, editor, first.id)
    editor.text_edit.insertPlainText("First content")
    session.select_card(second.id)
    assert editor.card_id == first.id
    assert editor.text_edit.toPlainText() == "First content"
    editor.text_edit.insertPlainText(" changed")
    editor.flush_pending()
    assert html_text(cards.get(first.id).content).strip() == "First content changed"
    assert html_text(cards.get(second.id).content).strip() == ""
    session.clear_selection()
    assert editor.card_id == first.id
    assert binding.card_id == first.id


def test_deleting_document_clears_editor_and_disposes_binding(qtbot):
    cards = CardCollection()
    card = cards.create("Card")
    session = CardsService(cards)
    editor = CardEditorWidget()
    qtbot.addWidget(editor)
    binding = CardEditorBinding(session, editor, card.id)
    session.core.delete(card.id)
    assert binding.is_disposed
    assert editor.card_id is None
    assert not editor.text_edit.isEnabled()
    assert editor.text_edit.toPlainText() == ""
