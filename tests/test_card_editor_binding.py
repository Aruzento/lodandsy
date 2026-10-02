from lodandsy.application.application_session import (
    ApplicationSession,
)
from lodandsy.application.card_editor_binding import (
    CardEditorBinding,
)
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.card_editor import CardEditorWidget


def test_editor_binding_updates_card_content(
    qtbot,
) -> None:
    cards = CardCollection()

    card = cards.create("Card")
    card.content = "Original"

    session = ApplicationSession(cards)

    editor = CardEditorWidget()
    qtbot.addWidget(editor)

    binding = CardEditorBinding(
        session,
        editor,
    )

    session.select_card(card.id)

    editor.text_edit.setPlainText(
        "Changed"
    )

    assert cards.get(card.id).content == "Changed"
    assert binding.session is session


def test_switching_cards_preserves_content(
    qtbot,
) -> None:
    cards = CardCollection()

    first = cards.create("First")
    first.content = "# First"

    second = cards.create("Second")
    second.content = "# Second"

    session = ApplicationSession(cards)

    editor = CardEditorWidget()
    qtbot.addWidget(editor)

    binding = CardEditorBinding(
        session,
        editor,
    )

    session.select_card(first.id)

    editor.text_edit.setPlainText(
        "# First changed"
    )

    session.select_card(second.id)

    assert (
        editor.text_edit.toPlainText()
        == "# Second"
    )

    editor.text_edit.setPlainText(
        "# Second changed"
    )

    session.select_card(first.id)

    assert (
        editor.text_edit.toPlainText()
        == "# First changed"
    )

    assert (
        cards.get(first.id).content
        == "# First changed"
    )

    assert (
        cards.get(second.id).content
        == "# Second changed"
    )

    assert binding.session is session


def test_clearing_selection_clears_editor(
    qtbot,
) -> None:
    cards = CardCollection()
    card = cards.create("Card")

    session = ApplicationSession(cards)

    editor = CardEditorWidget()
    qtbot.addWidget(editor)

    binding = CardEditorBinding(
        session,
        editor,
    )

    session.select_card(card.id)
    session.clear_selection()

    assert editor.card_id is None
    assert editor.text_edit.toPlainText() == ""
    assert not editor.text_edit.isEnabled()

    assert binding.session is session