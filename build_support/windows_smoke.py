"""Run the actual application workflows in a disposable project, including frozen Qt."""

import argparse
import json
import sys
import tempfile
import time
from contextlib import ExitStack
from dataclasses import asdict, replace
from pathlib import Path

import PySide6
from PySide6.QtCore import QEvent, QSettings, Qt, QTimer
from PySide6.QtGui import QImage, QKeyEvent, QPainterPath
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLineEdit, QMessageBox

from lodandsy import APP_VERSION
from lodandsy.application.app_controller import AppController
from lodandsy.application.clipboard import (
    INVENTORY_MIME,
    clipboard_writer,
    decode_inventory_transfer,
)
from lodandsy.application.project_catalogue import ProjectCatalogue
from lodandsy.application.project_controller import ProjectController
from lodandsy.application.project_history import ProjectHistory
from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.application.workspace_state import capture_workspace
from lodandsy.domain.currency import CUSTOM, RATE_SCALE, CoinAmount
from lodandsy.domain.item_categories import STANDARD_CATEGORIES
from lodandsy.domain.map_document import MapGrid, MapPortal, MapShape
from lodandsy.domain.table_document import ColumnDefinition, RowRecord
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.game_labels import ATTRIBUTES_PAGE, MODIFIERS_PAGE
from lodandsy.ui.modifier_editor import ModifierDialog
from lodandsy.ui.project_chooser import ProjectChooser
from lodandsy.ui.project_name_dialog import ProjectNameDialog
from lodandsy.ui.theme import apply_theme


def wait(app, predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise RuntimeError("Smoke workflow timed out")
        app.processEvents()
        if getattr(app, "smoke_errors", []):
            raise AssertionError("; ".join(app.smoke_errors))
        time.sleep(0.005)


def copy_and_wait(app, action, expected):
    messages = []
    receiver = messages.append
    writer = clipboard_writer()
    writer.message.connect(receiver)
    try:
        action()
        wait(app, lambda: bool(messages))
        assert messages[-1] == "Скопировано", messages[-1]
        assert QApplication.clipboard().text() == expected
    finally:
        writer.message.disconnect(receiver)


def managed_projects_smoke(app, project, root, screenshots):
    def capture(widget, filename):
        if screenshots:
            screenshots.mkdir(parents=True, exist_ok=True)
            app.processEvents()
            assert widget.grab().save(str(screenshots / filename))

    catalogue = project.catalogue
    assert catalogue.entries(()) == ()
    assert not catalogue.root.exists()
    empty = ProjectChooser((), welcome=True, root=catalogue.root)
    empty.show()
    capture(empty, "01-welcome-empty.png")
    empty.close()
    dialog = ProjectNameDialog(
        catalogue.destination,
        lambda name: project.create_project(name, preserve_current=False),
        project.window,
    )
    dialog.show()
    dialog.name.setText("Этар и окрестности")
    assert str(catalogue.root / dialog.name.text()) == dialog.path.text()
    capture(dialog, "02-create-project.png")
    dialog.confirm.click()
    assert not dialog.isVisible() and project.store.root.name == "Этар и окрестности"
    assert project.store.root.parent == catalogue.root
    card = project.controller.create_card("Ворота Этара")
    assert project.save_current()
    backup = root / "Этар — резервная копия.lodbackup"
    project.store.backup(backup)
    assert project.restore_project(backup, "Этар из копии")
    assert project.store.load().cards[0].id == card.id
    assert {entry["title"] for entry in catalogue.entries(())} == {
        "Этар и окрестности", "Этар из копии",
    }
    welcome = ProjectChooser(
        catalogue.entries(project.history.entries), welcome=True, root=catalogue.root,
    )
    welcome.show()
    capture(welcome, "03-welcome-projects.png")
    welcome.close()


def economy_smoke(app, controller, project, root, screenshots):
    def capture(widget, name):
        if screenshots:
            screenshots.mkdir(parents=True, exist_ok=True)
            app.processEvents()
            assert widget.grab().save(str(screenshots / (name + ".png")))

    world = root / "Синтетическая экономика"
    assert project.create_project(world, preserve_current=False)
    currency = controller.economy.currency
    settings = controller.open_economy()
    assert settings.table.rowCount() == 5
    capture(controller.settings_window, "01-currency-standard")
    controller.settings_window.reject()
    owner = controller.create_card("Дозорный Мира", card_type="character")
    section = next(s for s in owner.sections if s.purpose == "inventory")
    table = controller.actions.section_table(owner.id, section.id)
    wallet = tuple(
        CoinAmount(denom.id, count)
        for denom, count in zip(currency.denominations, (2, 12, 3, 6, 14))
    )
    controller.actions.set_wallet(table.id, wallet, expected=())
    for title, price, weight, eligible, category in (
        ("Клинок дозорного", 12, 3, True, 0),
        ("Зелье ясности", 5, 0.5, True, 3),
        ("Рунный осколок", 5, 0.25, True, 4),
        ("Связка отмычек", 2, 1, False, 2),
        ("Печать смотрителя", None, 0.1, False, 5),
    ):
        item = controller.create_card(title, card_type="item")
        controller.cards_service.update_card_fields(item.id, {
            "cost": CoinAmount(currency.base_id, price) if price is not None else None,
            "weight": weight, "loot_enabled": eligible,
            "item_category": STANDARD_CATEGORIES[category].id,
        })

    loot = controller.loot.open()
    assert controller.loot.open() is loot
    view = loot.widget()
    controller.loot.rng.seed(41)
    for control in view.count:
        control.setValue(3)
    view.budget[0].setText("17")
    view.budget[1].setText("40")
    view.include_money.setChecked(True)
    view.money[0].setText("2")
    view.money[1].setText("4")
    view.generate_button.click()
    result = controller.loot.result
    assert 17 * RATE_SCALE <= result.total <= 40 * RATE_SCALE
    assert sum(stack.count for stack in result.items) == 3 and result.coins
    view.results.item(0, 4).setCheckState(Qt.CheckState.Checked)
    capture(view, "02-loot")
    loot.dock.setFloating()
    app.processEvents()
    floating = loot.dock.floatingDockContainer()
    assert floating.isWindow()
    floating.resize(440, 490)
    capture(floating, "03-loot-floating")
    view.copy_button.click()
    clipboard = QApplication.clipboard()
    wait(app, lambda: clipboard.mimeData() is not None
         and clipboard.mimeData().hasFormat(INVENTORY_MIME))
    mime = bytes(clipboard.mimeData().data(INVENTORY_MIME))
    assert decode_inventory_transfer(mime).items == result.items
    inventory = controller.tables.open_table(table.id).widget()

    def confirm_money():
        dialog = app.activeModalWidget()
        if isinstance(dialog, QMessageBox):
            dialog.button(QMessageBox.StandardButton.Yes).click()

    QTimer.singleShot(150, confirm_money)
    inventory.paste_selection()
    saved = controller.tables_service.get_table(table.id)
    assert len(saved.rows) == len(result.items)
    assert sum(currency.value(coin) for coin in saved.wallet) > sum(
        currency.value(coin) for coin in wallet
    )
    clipboard.clear()
    capture(inventory, "04-wallet")

    shop = controller.shop.open()
    assert controller.shop.open() is shop
    shop.widget().generate_button.click()
    assert shop.widget().results.rowCount() == 5
    assert "доступно 5" in shop.widget().summary.text()
    capture(shop.widget(), "05-shop")
    assert project.save_current()
    identity = project.store.project_id
    backup = root / "economy.lodbackup"
    project.store.backup(backup)
    restored = SQLiteProjectStore.restore(backup, root / "Лут восстановлен")
    try:
        assert restored.project_id == identity
        assert next(t for t in restored.load().tables if t.id == table.id).wallet == saved.wallet
    finally:
        restored.close()

    assert project.create_project(root / "Другие валюты", preserve_current=False)
    assert controller.loot.result is None and controller.shop.result is None
    assert project.store.project_id != identity
    settings = controller.open_economy()
    settings.system.setCurrentIndex(settings.system.findData(CUSTOM))
    settings.add_button.click()
    settings.table.setCurrentCell(1, 1)
    settings.table.item(1, 0).setText("Искра")
    settings.table.item(1, 1).setText("и")
    settings.table.item(1, 2).setText("0,00001")
    capture(controller.settings_window, "06-currency-custom")
    controller.settings_window.save.click()
    controller.settings_window.reject()
    assert controller.economy.currency.denominations[1].rate_units == 1
    assert project.save_current()
    project.open_project(world)
    assert project.store.project_id == identity
    assert controller.loot.result == result and controller.loot.locked
    assert controller.shop.result.available == 5
    reopened = controller.window_manager.find_window(controller.loot.key)
    assert reopened is not None and reopened.dock.floatingDockContainer().isWindow()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--large-map-image", type=Path)
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument("--project-screenshots", type=Path)
    args = parser.parse_args()
    app = QApplication([])
    apply_theme(app)
    translated_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
    assert translated_buttons.buttons()[0].text() == "Отмена"
    window = AppShell()
    controller = AppController(window)
    app.smoke_errors = []
    controller.maps._error = lambda error: app.smoke_errors.append(str(error))
    catalogue = tempfile.TemporaryDirectory(prefix="lodandsy-smoke-user-")
    project = ProjectController(
        controller,
        ProjectHistory(
            QSettings(str(Path(catalogue.name) / "user.ini"), QSettings.Format.IniFormat)
        ),
        ProjectCatalogue(lambda: Path(catalogue.name) / "Documents"),
    )
    window.show()
    try:
        with (
            tempfile.TemporaryDirectory(prefix="lodandsy-mvp-smoke-") as temporary,
            ExitStack() as cleanup,
        ):
            cleanup.callback(lambda: project.store.close() if project.store else None)
            cleanup.callback(controller.maps.shutdown)
            cleanup.callback(project.saver.shutdown)
            cleanup.callback(setattr, window, "close_guard", None)
            root = Path(temporary).resolve()
            project.create_project(root / "Мир с кириллицей")
            a = controller.create_card("Город", card_type="article")
            b = controller.create_card("Таверна", card_type="character")
            first = controller.open_card_editor(a.id)
            second = controller.open_card_editor(b.id)
            first.widget().text_edit.insertPlainText("Город\n\n" + "История " * 10)
            second.widget().text_edit.insertHtml(f'<a href="lodandsy://entity/{a.id}">Дом</a>')
            image = QImage(1200, 800, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.darkGreen)
            source = root / "Карта.png"
            assert image.save(str(source))
            controller.card_views.images.insert(first.widget(), source, "Изображение города")
            wait(app, lambda: not controller.media.importing)
            assert "assets/" in controller.cards.get(a.id).content
            controller.card_views.images.portrait(second.widget(), source)
            wait(app, lambda: not controller.media.importing)
            assert controller.cards.get(b.id).portrait.asset_id in project.assets
            portrait = controller.cards.get(b.id).portrait
            second.widget().portrait_panel.changed.emit(
                replace(portrait, crop=(0.2, 0.1, 0.4, 0.8))
            )
            notes = controller.cards_service.add_section(a.id, "Путевые заметки")
            first.widget().select_section(notes.id)
            first.widget().text_edit.insertPlainText("Независимый раздел")
            inventory = next(
                s for s in controller.cards.get(b.id).sections if s.purpose == "inventory"
            )
            inventory_table = controller.actions.section_table(b.id, inventory.id)
            assert controller.actions.section_table(b.id, inventory.id).id == inventory_table.id
            second.widget().select_section(inventory.id)
            embedded_inventory = second.widget()._embedded_tables[inventory.id]
            inventory_view = controller.tables.open_table(inventory_table.id).widget()
            inventory_view.add_row()
            item_card = controller.create_card("Стальной меч", card_type="item")
            base = controller.economy.currency.base_id
            controller.cards_service.update_card_fields(
                item_card.id, {"cost": CoinAmount(base, 0), "summary": "Сталь"}
            )
            assert inventory_view.model.setData(inventory_view.model.index(0, 0), item_card.id)
            assert embedded_inventory.model.data(embedded_inventory.model.index(0, 3)) == "0 зм"
            controller.cards_service.update_card_fields(item_card.id, {"cost": CoinAmount(base, 9)})
            assert embedded_inventory.model.data(embedded_inventory.model.index(0, 3)) == "9 зм"
            assert len(controller.tables_service.get_table(inventory_table.id).rows[0].cells) == 3
            controller.window_manager.close_window(f"table:{inventory_table.id}")
            progress = []
            controller.maps.import_progress.connect(progress.append)
            controller.maps.import_map(args.large_map_image or source, "Область")
            wait(app, lambda: not controller.maps.importing, timeout=120)
            assert any(0 < value < 100 for value in progress), "Worker progress pipe missing"
            document = next(iter(controller.maps_service.maps.values()))
            controller.actions.update_entity(document.id, parent_id=b.id)
            map_widget = controller.maps.open_map(document.id).widget()
            wait(app, lambda: map_widget.view._background is not None, timeout=120)
            map_widget.tools.shape_actions["cone"].trigger()
            assert map_widget.tool_state.active == "cone"
            for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                QApplication.sendEvent(
                    map_widget.view,
                    QKeyEvent(kind, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier),
                )
                assert map_widget.tool_state.active == (
                    "pan" if kind == QEvent.Type.KeyPress else "cone"
                )
            map_widget.tools.actions["fog_erase"].trigger()
            assert map_widget.fog_tools.mode == "erase" and not map_widget.vector_tools.enabled
            map_widget.tools.actions["select"].trigger()
            fog_path = QPainterPath()
            fog_path.addRect(50, 50, 200, 200)
            controller.maps_service.edit_fog(document.id, fog_path)
            presentation = controller.maps.open_presentation(document.id)
            wait(app, lambda: presentation.view._display_ready)
            assert presentation.view._fog_state is controller.maps_service.get_map(document.id).fog
            assert presentation.view._background.tiles is map_widget.view._background.tiles
            controller.maps.close_presentation(document.id)
            grid = MapGrid(True, 50, 10, 10, 0.5)
            controller.maps_service.edit_map(document.id, grid=grid)
            token = controller.maps_service.add_token(document.id, a.id, 120, 130)
            item_token = controller.maps_service.add_token(
                document.id, b.id, 220, 230, kind_override="item", cells_w=2, cells_h=2
            )
            assert item_token.card_id == b.id
            controller.cards_service.update_card_fields(a.id, {"summary": "Canonical summary"})
            assert map_widget.view._tokens[0].presentation.summary == "Canonical summary"
            from lodandsy.domain.actor_state import ActorRef
            from lodandsy.domain.modifiers import Modifier

            controller.cards_service.update_card_fields(b.id, {"hp_max": 100})
            player_ref = ActorRef(b.id, item_token.actor_id)
            controller.cards_service.update_actor(player_ref, {"hp_current": 70})
            controller.cards_service.set_player(b.id, True, actor_id=player_ref.actor_id)
            other_map = controller.maps_service.create_map("Actor links", document.asset_id)
            shared = controller.maps_service.add_token(other_map.id, b.id, 100, 100)
            assert shared.actor_id == item_token.actor_id
            controller.cards_service.update_card_fields(
                item_card.id, {"modifiers": (Modifier("constitution", operand=2),)}
            )
            own_table = controller.tables_service.get_table(
                controller.cards_service.get_actor(player_ref).inventory_id
            )
            activity = next(c for c in own_table.columns if c.key == "active")
            controller.tables_service.set_cell(
                own_table.id, own_table.rows[0].id, activity.id, True, parsed=True
            )
            assert controller.cards_service.effective(player_ref).get("constitution").value == 12
            actor_editor = controller.card_views.open_game_sheet(b.id, player_ref.actor_id).widget()
            assert actor_editor.current_section == ATTRIBUTES_PAGE
            assert actor_editor.game_sheet.context.currentData() == player_ref.actor_id
            game_binding = controller.card_views.game_bindings[b.id]
            game_binding.buffer("hp_current", "65")
            game_binding.commit("hp_current", "65")
            assert controller.cards_service.get_actor(player_ref).value("hp_current") == 65
            controller.maps.focus_token(document.id, item_token.id)
            assert window.inspector_panel.field_form.controls["hp_current"].text() == "65"
            item_editor = controller.card_views.open_game_sheet(item_card.id).widget()
            assert item_editor.current_section == MODIFIERS_PAGE
            modifier_dialog = ModifierDialog(asdict(Modifier("constitution", operand=2)), window)
            modifier_dialog.search.setText("телосложение")
            assert modifier_dialog.target.findData("constitution") >= 0
            modifier_dialog.target.setCurrentIndex(modifier_dialog.target.findData("constitution"))
            assert modifier_dialog.target.currentData() == "constitution"
            assert not modifier_dialog.target.isEditable()
            modifier_dialog.reject()
            controller.window_manager.close_window(controller.card_editor_window_key(item_card.id))
            controller.cards_service.update_card_fields(b.id, {"ac_mode": "auto", "dexterity": 16})
            assert controller.cards_service.effective(player_ref).get("ac").value == 13
            for kind, category, base, expected_ac in (
                ("armor", "heavy", 18, 18),
                ("shield", None, None, 20),
            ):
                equipment = controller.create_card("Тестовая экипировка", card_type="item")
                controller.cards_service.update_card_fields(
                    equipment.id,
                    {
                        "equipment_kind": kind,
                        "armor_category": category,
                        "armor_ac": base,
                    },
                )
                inventory = controller.tables_service.get_table(own_table.id)
                record = inventory.new_row()
                controller.tables_service.edit_table(inventory.id, rows=(*inventory.rows, record))
                item_column = next(c for c in inventory.columns if c.key == "item")
                controller.tables_service.set_cell(
                    inventory.id, record.id, item_column.id, equipment.id
                )
                controller.actions.set_inventory_activity(inventory.id, record.id, True)
                assert controller.cards_service.effective(player_ref).get("ac").value == expected_ac
            controller.cards_service.update_actor(player_ref, {"ac_override": 21})
            controller.actions.set_inventory_activity(inventory.id, record.id, False)
            assert controller.cards_service.effective(player_ref).get("ac").value == 21
            controller.cards_service.update_actor(player_ref, {"ac_override": None})
            assert controller.cards_service.effective(player_ref).get("ac").value == 18
            controller.card_views.game_bindings[b.id].open_armor()
            assert controller.card_views.game_bindings[b.id].armor_dialog.isVisible()
            controller.card_views.game_bindings[b.id].armor_dialog.close()
            npc = controller.create_card("Goblin", card_type="creature")
            controller.cards_service.update_card_fields(npc.id, {"hp_max": 20})
            npc_token = controller.maps_service.add_token(other_map.id, npc.id, 200, 200)
            controller.cards_service.update_actor(
                ActorRef(npc.id, npc_token.actor_id), {"hp_current": 7}
            )
            copied = controller.actions.copy_token(other_map.id, npc_token.id)
            assert copied.actor_id != npc_token.actor_id
            assert (
                controller.cards_service.get_actor(ActorRef(npc.id, copied.actor_id)).value(
                    "hp_current"
                )
                == 20
            )
            rule_editor = controller.open_rules()
            assert controller.rules_action.isEnabled()
            rule_editor.select_formula("constitution_mod")
            rule_editor.example_controls["constitution"].setText("16")
            rule_editor.test_example()
            assert rule_editor.status.text() == "Результат: 3"
            rule_editor.select_formula("initiative")
            rule_editor.expression.setPlainText("dexterity_mod + 1")
            rule_editor.check_project()
            assert rule_editor.preview is not None
            rule_editor.apply_project()
            assert (
                dict(controller.cards_service.rules.overrides)["initiative"] == "dexterity_mod + 1"
            )
            controller.settings_window.reject()
            app.processEvents()
            window.activateWindow()
            print("Smoke: actors, inventory and project rules passed", flush=True)
            layer = controller.maps_service.add_layer(document.id, "Decor")
            other_layer = controller.maps_service.add_layer(document.id, "Upper")
            controller.maps_service.add_object(
                document.id, layer.id, document.asset_id, 10, 20, 100, 80
            )
            controller.maps_service.add_object(
                document.id, other_layer.id, document.asset_id, 110, 120, 100, 80
            )
            map_editor = controller.maps.open_map_editor(document.id).widget()
            assert map_editor is not map_widget and len(map_editor.view._objects) == 2
            object_card = controller.actions.create_object_card("Декорация", portrait.asset_id)
            map_editor.select_library_card(object_card.id)
            assert object_card.id in map_editor.library_model.ids
            controller.maps._editor_place(document.id, layer.id, object_card.id, 300, 300)
            decor = controller.maps_service.get_map(document.id).objects[-1]
            assert decor.width == 128 and abs(decor.height - 128 * 800 / 1200) < 1e-6
            controller.cards_service.update_card_fields(
                object_card.id, {"title": "Объект переименован"}
            )
            assert map_editor.assets.currentIndex().data(Qt.ItemDataRole.UserRole) == object_card.id
            assert map_editor.layers.item(0).data(Qt.ItemDataRole.UserRole) == other_layer.id
            controller.maps_service.edit_layer(document.id, other_layer.id, visible=False)
            controller.maps_service.move_token(document.id, token.id, 190, 190)
            assert controller.maps_service.get_map(document.id).tokens[0].x == 190
            controller.maps_service.undo_stack(document.id).undo()
            assert controller.maps_service.get_map(document.id).tokens[0].x == token.x
            table = controller.tables_service.create_table("Встречи")
            controller.actions.update_entity(table.id, parent_id=document.id)
            columns = (
                ColumnDefinition("Событие"),
                ColumnDefinition("Количество", "number", 1),
                ColumnDefinition("Есть", "bool", 2),
            )
            controller.tables_service.edit_table(
                table.id,
                columns=columns,
                rows=(
                    RowRecord(
                        0, ((columns[0].id, "Купец"), (columns[1].id, 0), (columns[2].id, False))
                    ),
                    RowRecord(1),
                ),
            )
            table_widget = controller.tables.open_table(table.id).widget()
            wait(app, table_widget.isVisible)
            window.raise_()
            window.activateWindow()
            wait(app, window.isActiveWindow)
            table_widget.table.setFocus()
            wait(app, table_widget.table.hasFocus)
            table_widget.table.setCurrentIndex(table_widget.model.index(0, 0))
            table_widget.table.edit(table_widget.model.index(0, 0))
            app.processEvents()
            control = next(e for e in table_widget.table.findChildren(QLineEdit) if e.isVisible())
            control.selectAll()
            for character in "Дракон":
                QApplication.sendEvent(
                    control,
                    QKeyEvent(QEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, character),
                )
            assert control.text() == "Дракон"
            assert project.save_current()
            assert control.isUndoAvailable()
            QApplication.sendEvent(
                control,
                QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
            )
            app.processEvents()
            assert table_widget.model.data(table_widget.model.index(0, 0)) == "Дракон"
            table_widget.table.selectRow(0)
            copy_and_wait(app, table_widget.copy_selection, "Дракон\t0\tfalse")
            assert not table_widget.model.setData(table_widget.model.index(0, 1), "bad")
            assert project.draft_count == 1
            assert project.save_current()
            assert (
                next(t for t in project.store.load().tables if t.id == table.id)
                .rows[0]
                .value(columns[1].id)
                == 0
            )
            project.discard_drafts()
            dice = controller.dice.open().widget()
            dice.counts[20].setValue(0)
            dice.counts[6].setValue(3)
            dice.counts[100].setValue(1)
            dice.modifier.setValue(-2)
            dice.throw()
            assert " = " in dice.result.toPlainText()
            assert "d100:" in dice.result.toPlainText()
            copy_and_wait(app, dice.copy.click, dice.result.toPlainText())
            shape = MapShape("circle", ((64, 0),), x=300, y=300, name="Публичная область")
            portal = MapPortal(other_map.id, 400, 400, "Скрытое имя", hide_label=True)
            controller.maps_service.put_vector(document.id, shape)
            controller.maps_service.put_vector(document.id, portal)
            presentation = controller.maps.open_presentation(document.id)
            wait(app, lambda: presentation.view._display_ready)
            assert presentation.view.vector_shapes == (shape,)
            assert not presentation.view.vector_portals
            controller.maps._portal_open(document.id, portal.id)
            assert controller.maps.presentations[other_map.id] is presentation
            wait(app, lambda: presentation.view._display_ready)
            controller.maps._token_action(other_map.id, shared.id, "portrait")
            assert len(controller.maps._portrait_views) == 2
            overlay = controller.maps._portrait_views[0]
            wait(
                app,
                lambda: (
                    (image := overlay.provider(overlay.root, overlay.path)) is not None
                    and not image.isNull()
                ),
            )
            original = overlay.provider(overlay.root, overlay.path)
            assert 1.49 < original.width() / original.height() < 1.51
            controller.maps._portrait_views[1].dismissed.emit()
            assert controller.maps._portrait is None
            controller.maps.close_presentation(other_map.id)
            controller.window_manager.close_window("map:" + other_map.id)
            assert len(controller.window_manager.window_keys()) == 6
            second.dock.setFloating()
            app.processEvents()
            assert second.dock.floatingDockContainer().isWindow()
            assert project.save_current()
            note = controller.actions.create_map_note(
                document.id, "note", "Заметка для ведущего", 180, 190,
            )
            inventory = controller.actions.create_map_note(
                document.id, "inventory", "Припасы карты", 230, 190,
            )
            assert controller.core.entities.get(note.target_id).parent_id == document.id
            assert controller.actions.inventory_owner(inventory.target_id) == document.id
            map_wallet = (CoinAmount(controller.economy.currency.base_id, 2),)
            controller.actions.set_wallet(inventory.target_id, map_wallet, expected=())
            controller.maps_service.edit_token(document.id, item_token.id, hidden=True, dead=True)
            presentation = controller.maps.open_presentation(document.id)
            wait(app, lambda: presentation.view._display_ready)
            assert not presentation.view.vector_notes
            assert item_token.id not in {item.token.id for item in presentation.view._tokens}
            controller.maps.close_presentation(document.id)
            assert project.save_current()
            assert list(project.store.root.parent.glob("LODANDSY-before-Map11-*.lodbackup"))
            expected = project.store.load()
            print("Smoke: snapshot saved", flush=True)
            project._save_ui_state()
            assert capture_workspace(controller)["documents"]
            print("Smoke: backup begin", flush=True)
            backup = root / "backup.lodbackup"
            project.store.backup(backup)
            print("Smoke: restore archive begin", flush=True)
            restored = SQLiteProjectStore.restore(backup, root / "Восстановлено")
            assert restored.load() == expected
            restored.close()
            print("Smoke: open restored project", flush=True)
            project.open_project(root / "Восстановлено")
            assert controller.tables_service.get_table(inventory.target_id).wallet == map_wallet
            restored_map = controller.maps.open_map(document.id).widget()
            wait(app, lambda: restored_map.view._background is not None, timeout=120)
            print("Smoke: reopen source project", flush=True)
            project.open_project(root / "Мир с кириллицей")
            reopened_map = controller.maps.open_map(document.id).widget()
            wait(app, lambda: reopened_map.view._background is not None, timeout=120)
            wait(app, lambda: len(controller.window_manager.window_keys()) == 6)
            assert project.store.load() == expected
            controller.delete_card(a.id)
            assert len(controller.maps_service.get_map(document.id).tokens) == 1
            assert controller.cards.get(b.id)
            assert project.save_current()
            economy_smoke(app, controller, project, root, args.screenshots)
            managed_projects_smoke(app, project, root, args.project_screenshots)
            result = {
                "map11_hidden_tokens_and_gm_notes": True,
                "map_note_owns_distinct_child_document_and_inventory_wallet": True,
                "player_presentation_shared_tiles_vector_fog": True,
                "passed": True,
                "frozen": bool(getattr(sys, "frozen", False)),
                "python": sys.version,
                "qt": PySide6.__version__,
                "platform": app.platformName(),
                "app_version": APP_VERSION,
                "cards_maps_tools_sqlite": True,
                "backup_restore": True,
                "independent_windows": True,
                "layout_reopen": True,
                "card_placements_cascade_atomically": True,
                "layers_raster_objects": True,
                "canonical_card_fields": True,
                "actors_player_npc_copy_inventory": True,
                "project_formula_editor_and_overrides": True,
                "virtual_game_pages_and_explicit_actor_context": True,
                "typed_russian_modifier_catalog_and_rules_example": True,
                "native_qt_russian_translation": True,
                "typed_inventory_equipment_ac_and_manual_final": True,
                "map_m5_shapes_portal_original_image": True,
                "map_m55_native_toolbar_and_space": True,
                "map9_portal_hidden_label_backup_reopen": True,
                "table_then_dice_native_clipboard": True,
                "unicode_paths": True,
                "uuid_sections_child_inventory_crop": True,
                "reference_inventory_projections_no_copies": True,
                "semantic_native_keyboard_flush": True,
                "object_card_library_original_aspect": True,
                "front_layer_at_top": True,
                "independent_map_editor_free_tokens": True,
                "typed_table_and_nonblocking_drafts": True,
                "application_dice_tool": True,
                "economy_t3_price_wallet_clipboard_loot_shop": True,
                "economy_t3_project_isolation_floating_and_restore": True,
                "mixed_entity_hierarchy": True,
                "managed_project_name_catalogue_and_restore": True,
                "large_map_supplied": bool(args.large_map_image),
                "manual_acceptance": "not performed by this automated smoke",
            }
            args.report.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print("Smoke: passed; report " + str(args.report), flush=True)
    finally:
        window.close_guard = None
        window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
