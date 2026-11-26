from PySide6.QtCore import Qt

from lodandsy.application.app_controller import AppController
from lodandsy.application.card_editor_binding import (
    CardEditorBinding,
)
from lodandsy.application.rich_html import text_document
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.card_editor import CardEditorWidget
from lodandsy.ui.icons import tree_card_icon

pytest_plugins = ["tests.project_fixture"]


def test_tree_icons_follow_canonical_type_through_rename_move_and_project_reload(
    project, tmp_path,
):
    app, projects = project
    path = tmp_path / "Мир"
    assert projects.create_project(path)
    panel = app.window.tree_panel
    model = panel.tree_model
    folder = app.create_card("Папка", card_type="folder")
    item = app.create_card("Ту же строку можно назвать как угодно", folder.id, card_type="item")
    note = app.create_card(item.title, folder.id, card_type="note")
    folder_key, item_key = f"card:{folder.id}", f"card:{item.id}"

    def check_icons():
        for card in (folder, item, note):
            index = model.index_for_node(f"card:{card.id}")
            assert index.data(Qt.ItemDataRole.DecorationRole).cacheKey() == tree_card_icon(
                card.card_type
            ).cacheKey()

    check_icons()
    panel.tree_view.expand(model.index_for_node(folder_key))
    panel.select_node(item_key)
    app.rename_card(item.id, "Запись о находке")
    check_icons()
    mime = model.mimeData([model.index_for_node(item_key)])
    assert model.dropMimeData(
        mime, Qt.DropAction.MoveAction, 2, 0, model.index_for_node(folder_key)
    )
    assert model.index_for_node(item_key).row() == 1
    assert panel.tree_view.isExpanded(model.index_for_node(folder_key))
    assert panel.current_node_key() == item_key
    check_icons()
    assert projects.save_current()
    assert projects.create_project(tmp_path / "Другой мир", preserve_current=False)
    assert not model.index_for_node(item_key).isValid()
    projects.open_project(path)
    assert model.index_for_node(item_key).data() == "Запись о находке"
    assert model.index_for_node(item_key).row() == 1
    check_icons()


def test_tree_selection_updates_session(
    qtbot,
) -> None:
    cards = CardCollection()

    world = cards.create("World")

    city = cards.create(
        "City",
        parent_id=world.id,
    )

    window = AppShell()
    qtbot.addWidget(window)

    controller = AppController(
        window,
        cards,
    )

    model = window.tree_panel.tree_model

    world_index = model.index_for_node("card:" + world.id)

    city_index = model.index(
        0,
        0,
        world_index,
    )

    with qtbot.waitSignal(
        controller.cards_service.current_card_changed,
        timeout=1000,
    ) as signal:
        window.tree_panel.tree_view.setCurrentIndex(city_index)

    assert signal.args == [city.id]

    assert controller.cards_service.current_card_id == city.id

    assert controller.cards_service.current_card is city


def test_tree_can_switch_session_selection(
    qtbot,
) -> None:
    cards = CardCollection()

    world = cards.create("World")

    city = cards.create(
        "City",
        parent_id=world.id,
    )

    window = AppShell()
    qtbot.addWidget(window)

    controller = AppController(
        window,
        cards,
    )

    model = window.tree_panel.tree_model

    world_index = model.index_for_node("card:" + world.id)

    city_index = model.index(
        0,
        0,
        world_index,
    )

    window.tree_panel.tree_view.setCurrentIndex(world_index)

    assert controller.cards_service.current_card_id == world.id

    window.tree_panel.tree_view.setCurrentIndex(city_index)

    assert controller.cards_service.current_card_id == city.id


def test_tree_selection_updates_editor_and_inspector(
    qtbot,
) -> None:
    cards = CardCollection()

    world = cards.create("World")
    world = cards.update(world.id, content=text_document("# World"))

    city = cards.create(
        "City",
        parent_id=world.id,
    )
    city = cards.update(city.id, content=text_document("# City"))

    window = AppShell()
    qtbot.addWidget(window)

    controller = AppController(
        window,
        cards,
    )

    editor = CardEditorWidget()
    qtbot.addWidget(editor)

    editor_binding = CardEditorBinding(
        controller.cards_service,
        editor,
        city.id,
    )

    model = window.tree_panel.tree_model

    world_index = model.index_for_node("card:" + world.id)

    city_index = model.index(
        0,
        0,
        world_index,
    )

    window.tree_panel.tree_view.setCurrentIndex(city_index)

    assert controller.cards_service.current_card_id == city.id

    assert editor.card_id == city.id
    assert editor.text_edit.toPlainText() == "# City"

    assert window.inspector_panel.id_edit.text() == city.id

    assert window.inspector_panel.title_edit.text() == "City"

    assert editor_binding.session is controller.cards_service


def test_deleting_selected_card_clears_session_and_views(
    qtbot,
) -> None:
    cards = CardCollection()

    world = cards.create("World")

    city = cards.create(
        "City",
        parent_id=world.id,
    )
    city = cards.update(city.id, content=text_document("# City"))

    window = AppShell()
    qtbot.addWidget(window)

    controller = AppController(
        window,
        cards,
    )

    editor = CardEditorWidget()
    qtbot.addWidget(editor)

    editor_binding = CardEditorBinding(
        controller.cards_service,
        editor,
        city.id,
    )

    model = window.tree_panel.tree_model

    world_index = model.index_for_node("card:" + world.id)

    city_index = model.index(
        0,
        0,
        world_index,
    )

    window.tree_panel.tree_view.setCurrentIndex(city_index)

    assert controller.cards_service.current_card_id == city.id

    controller.delete_card(city.id)

    assert controller.cards_service.current_card_id is None
    assert controller.cards_service.current_card is None

    assert editor.card_id is None
    assert not editor.text_edit.isEnabled()

    assert window.inspector_panel.id_edit.text() == ""
    assert not window.inspector_panel.title_edit.isEnabled()

    assert editor_binding.session is controller.cards_service
