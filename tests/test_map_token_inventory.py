from dataclasses import replace

from PySide6.QtCore import QMimeData, QPoint, Qt
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox

from lodandsy.application.clipboard import INVENTORY_MIME, encode_inventory_transfer
from lodandsy.domain.actor_state import ActorRef
from lodandsy.domain.currency import CoinAmount
from lodandsy.domain.inventory_transfer import InventoryTransfer, ItemStack
from tests.test_map_tokens_grid import open_map

pytest_plugins = ["tests.project_fixture"]


def token_inventory(viewer, token, monkeypatch, *, enabled=True):
    class InventoryMenu(QMenu):
        def exec(self, _point):
            action = next(action for action in self.actions() if action.data() == "inventory")
            assert action.text() == "Открыть инвентарь"
            assert not action.icon().isNull()
            assert action.isEnabled() == enabled
            return action if enabled else None

    class Event:
        def screenPos(self):
            return QPoint()

        def accept(self):
            pass

    with monkeypatch.context() as context:
        context.setattr("lodandsy.ui.map_annotations.QMenu", InventoryMenu)
        item = next(item for item in viewer.view._tokens if item.token.id == token.id)
        item.contextMenuEvent(Event())


def test_inventory_window_floats_and_follows_placement_identity(
    project, tmp_path, qtbot, monkeypatch
):
    app, projects = project
    document, viewer = open_map(app, projects, tmp_path, qtbot)
    card = app.create_card("Страж", card_type="character")
    first = app.actions.place_card(document.id, card.id, 65, 65)
    second = app.actions.place_card(document.id, card.id, 180, 65)
    ref = ActorRef(card.id, first.actor_id)
    actor = app.cards_service.get_actor(ref)
    another = app.cards_service.get_actor(ActorRef(card.id, second.actor_id))
    assert actor.inventory_id != another.inventory_id

    window = app.tables.open_table(actor.inventory_id)
    widget = window.widget()
    assert not window.dock.isInFloatingContainer()
    token_inventory(viewer, first, monkeypatch)
    assert window.dock.isInFloatingContainer()
    assert window.widget() is widget
    assert window.windowTitle() == f"Инвентарь — {actor.name}"
    token_inventory(viewer, second, monkeypatch)
    another_window = app.window_manager.find_window(f"table:{another.inventory_id}")
    assert another_window is not window and another_window.dock.isInFloatingContainer()
    token_inventory(viewer, first, monkeypatch)
    assert app.window_manager.active_window_key == window.key
    assert app.window_manager.find_window(window.key) is window
    base = app.economy.currency.base_id
    widget.wallet.controls[(actor.inventory_id, base)].commit_requested.emit("5")
    assert widget.model.document.wallet == (CoinAmount(base, 5),)
    assert another_window.widget().model.document.wallet == ()

    app.cards_service.update_actor(ref, {"actor_name": "Старший страж"})
    assert window.windowTitle() == "Инвентарь — Старший страж"
    app.actions.delete_actor(ref, confirmed=True)
    assert app.window_manager.find_window(window.key) is None
    assert app.window_manager.find_window(another_window.key) is another_window
    viewer.view.token_action.emit(first.id, "inventory")
    assert app.window_manager.find_window(window.key) is None

    app.cards_service.update_card(
        card.id, actors=(replace(another, inventory_id=None),),
    )
    assert app.cards_service.get_actor(ActorRef(card.id, second.actor_id)).inventory_id is None
    token_inventory(viewer, second, monkeypatch, enabled=False)


def test_player_inventory_is_shared_and_keeps_edits_on_reopen(
    project, tmp_path, qtbot, monkeypatch
):
    app, projects = project
    first_map, first_view = open_map(app, projects, tmp_path, qtbot)
    second_map = app.maps_service.create_map("Другая карта", first_map.asset_id)
    second_view = app.maps.open_map(second_map.id).widget()
    card = app.create_card("Герой", card_type="character", player=True)
    app.cards_service.update_card_fields(card.id, {"dexterity": 16})
    first = app.actions.place_card(first_map.id, card.id, 90, 90)
    second = app.actions.place_card(second_map.id, card.id, 100, 90)
    ref = ActorRef(card.id, first.actor_id)
    actor = app.cards_service.get_actor(ref)
    assert first.actor_id == second.actor_id

    token_inventory(first_view, first, monkeypatch)
    window = app.window_manager.find_window(f"table:{actor.inventory_id}")
    token_inventory(second_view, second, monkeypatch)
    assert app.window_manager.find_window(window.key) is window
    table = window.widget()
    other_view = app.tables.embedded_view(actor.inventory_id, card.id)
    qtbot.addWidget(other_view)
    armor = app.create_card("Доспех", card_type="item")
    app.cards_service.update_card_fields(
        armor.id, {"equipment_kind": "armor", "armor_category": "medium", "armor_ac": 14},
    )
    base = app.economy.currency.base_id
    transfer = InventoryTransfer(
        projects.store.project_id, (ItemStack(armor.id, 2),), (CoinAmount(base, 3),),
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    mime = QMimeData()
    mime.setData(INVENTORY_MIME, encode_inventory_transfer(transfer))
    clipboard = QApplication.clipboard()
    clipboard.setMimeData(mime)
    try:
        table.paste_selection()
    finally:
        clipboard.clear()
    assert other_view.model.document is table.model.document
    assert table.model.rowCount() == 1
    assert table.model.data(table.model.index(0, 0)) == "Доспех"
    table.open_reference(table.model.index(0, 0))
    assert app.window_manager.active_window_key == app.card_editor_window_key(armor.id)

    active_index = next(
        i for i, col in enumerate(table.model.document.columns) if col.key == "active"
    )
    assert other_view.model.setData(
        other_view.model.index(0, active_index), Qt.CheckState.Checked,
        Qt.ItemDataRole.CheckStateRole,
    )
    assert table.model.data(
        table.model.index(0, active_index), Qt.ItemDataRole.CheckStateRole,
    ) == Qt.CheckState.Checked
    assert app.cards_service.effective(ref).get("ac").value == 16
    address = actor.inventory_id, base
    count = table.wallet.controls[address]
    assert count.text() == other_view.wallet.controls[address].text() == "3"
    count.commit_requested.emit("8")
    assert other_view.wallet.controls[address].text() == "8"
    expected = table.model.document
    assert expected.wallet == (CoinAmount(base, 8),)
    assert projects.save_current()
    root, window_key = projects.store.root, window.key
    other_view.close()
    other_view.deleteLater()
    assert projects.create_project(tmp_path / "Другой мир", preserve_current=False)
    assert app.window_manager.find_window(window_key) is None
    projects.open_project(root)
    restored = app.window_manager.find_window(window_key)
    assert restored is not None and restored.dock.isInFloatingContainer()
    assert restored.widget().model.document == expected
    assert restored.widget().wallet.controls[address].text() == "8"
    assert app.cards_service.effective(ref).get("ac").value == 16
