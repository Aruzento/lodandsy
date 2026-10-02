from PySide6.QtCore import QModelIndex

from lodandsy.application.app_controller import AppController
from lodandsy.application.card_editor_binding import (
    CardEditorBinding,
)
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.card_editor import CardEditorWidget
from lodandsy.ui.card_tree_model import (
    CARD_ID_ROLE,
    CardTreeModel,
)


def _find_card_index(
    model: CardTreeModel,
    card_id: str,
    parent: QModelIndex = QModelIndex(),
) -> QModelIndex:
    for row in range(model.rowCount(parent)):
        index = model.index(
            row,
            0,
            parent,
        )

        if index.data(CARD_ID_ROLE) == card_id:
            return index

        child_result = _find_card_index(
            model,
            card_id,
            index,
        )

        if child_result.isValid():
            return child_result

    return QModelIndex()


def test_tree_editor_inspector_share_one_card_state(
    qtbot,
) -> None:
    cards = CardCollection()

    world = cards.create("World")
    world.content = "# World\n\nWorld text."

    kingdom = cards.create(
        "Kingdom",
        parent_id=world.id,
    )
    kingdom.content = "# Kingdom\n\nKingdom text."

    city = cards.create(
        "City",
        parent_id=kingdom.id,
    )
    city.content = "# City\n\nOriginal city text."

    window = AppShell()
    qtbot.addWidget(window)

    controller = AppController(
        window,
        cards,
    )

    editor = CardEditorWidget()
    qtbot.addWidget(editor)

    editor_binding = CardEditorBinding(
        controller.session,
        editor,
    )

    model = window.tree_panel.tree_model

    # 1. Select City through the real Tree.
    city_index = _find_card_index(
        model,
        city.id,
    )

    assert city_index.isValid()

    window.tree_panel.tree_view.setCurrentIndex(
        city_index
    )

    assert controller.session.current_card_id == city.id
    assert controller.session.current_card is city
    assert controller.session.current_card is cards.get(city.id)

    assert editor.card_id == city.id
    assert (
        editor.text_edit.toPlainText()
        == "# City\n\nOriginal city text."
    )

    assert (
        window.inspector_panel.id_edit.text()
        == city.id
    )
    assert (
        window.inspector_panel.title_edit.text()
        == "City"
    )
    assert (
        window.inspector_panel.parent_combo.currentData()
        == kingdom.id
    )

    # 2. Change content through Editor.
    editor.text_edit.setPlainText(
        "# City\n\nChanged city text."
    )

    assert (
        cards.get(city.id).content
        == "# City\n\nChanged city text."
    )

    # 3. Rename through Inspector.
    window.inspector_panel.title_edit.setText(
        "Capital"
    )
    window.inspector_panel.title_edit.editingFinished.emit()

    assert cards.get(city.id).title == "Capital"

    city_index = _find_card_index(
        model,
        city.id,
    )

    assert city_index.isValid()
    assert city_index.data() == "Capital"

    # 4. Reparent City from Kingdom to World through Inspector.
    world_parent_index = next(
        index
        for index in range(
            window.inspector_panel.parent_combo.count()
        )
        if (
            window.inspector_panel.parent_combo.itemData(
                index
            )
            == world.id
        )
    )

    window.inspector_panel.parent_combo.setCurrentIndex(
        world_parent_index
    )

    assert (
        cards.get(city.id).parent_id
        == world.id
    )

    city_index = _find_card_index(
        model,
        city.id,
    )

    assert city_index.isValid()
    assert city_index.parent().data(CARD_ID_ROLE) == world.id

    # 5. Switch to another Card.
    world_index = _find_card_index(
        model,
        world.id,
    )

    assert world_index.isValid()

    window.tree_panel.tree_view.setCurrentIndex(
        world_index
    )

    assert controller.session.current_card_id == world.id
    assert controller.session.current_card is world

    assert editor.card_id == world.id
    assert (
        editor.text_edit.toPlainText()
        == "# World\n\nWorld text."
    )

    assert (
        window.inspector_panel.id_edit.text()
        == world.id
    )
    assert (
        window.inspector_panel.title_edit.text()
        == "World"
    )

    # 6. Return to City and verify all previous changes survived.
    city_index = _find_card_index(
        model,
        city.id,
    )

    assert city_index.isValid()

    window.tree_panel.tree_view.setCurrentIndex(
        city_index
    )

    assert controller.session.current_card_id == city.id
    assert controller.session.current_card is city

    assert city.title == "Capital"
    assert city.parent_id == world.id
    assert (
        city.content
        == "# City\n\nChanged city text."
    )

    assert editor.card_id == city.id
    assert (
        editor.text_edit.toPlainText()
        == "# City\n\nChanged city text."
    )

    assert (
        window.inspector_panel.id_edit.text()
        == city.id
    )
    assert (
        window.inspector_panel.title_edit.text()
        == "Capital"
    )
    assert (
        window.inspector_panel.parent_combo.currentData()
        == world.id
    )

    assert (
        _find_card_index(
            model,
            city.id,
        ).data()
        == "Capital"
    )

    assert editor_binding.session is controller.session