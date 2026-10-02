from lodandsy.ui.inspector_panel import InspectorPanel


def test_inspector_loads_card_without_emitting_changes(
    qtbot,
) -> None:
    panel = InspectorPanel()
    qtbot.addWidget(panel)

    title_changes: list[tuple[str, str]] = []
    parent_changes: list[
        tuple[str, str | None]
    ] = []

    panel.title_changed.connect(
        lambda card_id, title: (
            title_changes.append(
                (card_id, title)
            )
        )
    )

    panel.parent_changed.connect(
        lambda card_id, parent_id: (
            parent_changes.append(
                (card_id, parent_id)
            )
        )
    )

    panel.set_card(
        card_id="card-1",
        title="City",
        parent_id="world-1",
        parent_options=[
            (None, "Root"),
            ("world-1", "World"),
        ],
    )

    assert panel.id_edit.text() == "card-1"
    assert panel.title_edit.text() == "City"

    assert (
        panel.parent_combo.currentData()
        == "world-1"
    )

    assert title_changes == []
    assert parent_changes == []


def test_inspector_emits_title_change(
    qtbot,
) -> None:
    panel = InspectorPanel()
    qtbot.addWidget(panel)

    panel.set_card(
        card_id="card-1",
        title="Old title",
        parent_id=None,
        parent_options=[
            (None, "Root"),
        ],
    )

    with qtbot.waitSignal(
        panel.title_changed,
        timeout=1000,
    ) as signal:
        panel.title_edit.setText(
            "New title"
        )
        panel.title_edit.editingFinished.emit()

    assert signal.args == [
        "card-1",
        "New title",
    ]


def test_inspector_emits_parent_change(
    qtbot,
) -> None:
    panel = InspectorPanel()
    qtbot.addWidget(panel)

    panel.set_card(
        card_id="card-1",
        title="City",
        parent_id=None,
        parent_options=[
            (None, "Root"),
            ("world-1", "World"),
        ],
    )

    with qtbot.waitSignal(
        panel.parent_changed,
        timeout=1000,
    ) as signal:
        panel.parent_combo.setCurrentIndex(1)

    assert signal.args == [
        "card-1",
        "world-1",
    ]


def test_inspector_rejects_empty_title(
    qtbot,
) -> None:
    panel = InspectorPanel()
    qtbot.addWidget(panel)

    panel.set_card(
        card_id="card-1",
        title="City",
        parent_id=None,
        parent_options=[
            (None, "Root"),
        ],
    )

    panel.title_edit.setText("   ")
    panel.title_edit.editingFinished.emit()

    assert panel.title_edit.text() == "City"