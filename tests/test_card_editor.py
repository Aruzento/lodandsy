from lodandsy.ui.card_editor import CardEditorWidget


def test_editor_loads_card_without_emitting_change(
    qtbot,
) -> None:
    editor = CardEditorWidget()
    qtbot.addWidget(editor)

    changes: list[tuple[str, str]] = []

    editor.content_changed.connect(
        lambda card_id, content: changes.append(
            (card_id, content)
        )
    )

    editor.set_card(
        "card-1",
        "# Hello",
    )

    assert editor.card_id == "card-1"
    assert editor.text_edit.toPlainText() == "# Hello"
    assert changes == []


def test_editor_emits_content_change(
    qtbot,
) -> None:
    editor = CardEditorWidget()
    qtbot.addWidget(editor)

    editor.set_card(
        "card-1",
        "Old content",
    )

    with qtbot.waitSignal(
        editor.content_changed,
        timeout=1000,
    ) as signal:
        editor.text_edit.setPlainText(
            "New content"
        )

    assert signal.args == [
        "card-1",
        "New content",
    ]


def test_editor_can_be_cleared(
    qtbot,
) -> None:
    editor = CardEditorWidget()
    qtbot.addWidget(editor)

    editor.set_card(
        "card-1",
        "Content",
    )

    editor.clear_card()

    assert editor.card_id is None
    assert editor.text_edit.toPlainText() == ""
    assert not editor.text_edit.isEnabled()