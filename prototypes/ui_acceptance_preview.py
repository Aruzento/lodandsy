"""Render real production Qt views in an isolated disposable world for visual review."""

import argparse
import json
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.application.project_history import ProjectHistory
from lodandsy.domain.actor_state import ActorRef
from lodandsy.domain.modifiers import Modifier
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.modifier_editor import ModifierDialog
from lodandsy.ui.theme import apply_theme


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    with tempfile.TemporaryDirectory(prefix="lodandsy-ui-review-") as folder:
        root = Path(folder)
        window = AppShell()
        controller = AppController(window)
        project = ProjectController(
            controller,
            ProjectHistory(QSettings(str(root / "user.ini"), QSettings.Format.IniFormat)),
        )

        def settle(seconds=0.15):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.005)

        def capture(widget, name):
            settle()
            path = args.output / (name + ".png")
            assert widget.grab().save(str(path))
            print(name, widget.width(), widget.height(), flush=True)

        try:
            project.create_project(root / "Проверка интерфейса")
            window.resize(1450, 1000)
            window.show()
            card = controller.create_card("Альрик · Воин", card_type="character", player=True)
            service = controller.cards_service
            service.update_card_fields(
                card.id,
                {
                    "level": 5,
                    "strength": 16,
                    "dexterity": 12,
                    "constitution": 14,
                    "intelligence": 10,
                    "wisdom": 10,
                    "charisma": 8,
                    "hit_die": 10,
                    "hp_gains": (10, 6, 6, 6, 6),
                    "hp_max_mode": "auto",
                    "ac_mode": "auto",
                    "speed_mode": "auto",
                    "class_or_role": "Воин",
                    "subclass": "Чемпион",
                    "race": "Человек",
                    "athletics_proficiency": 1,
                    "constitution_save_proficient": True,
                },
            )
            ref = ActorRef(card.id, card.default_actor_id)
            service.update_actor(ref, {"hp_current": 32, "hp_temp": 5})
            item = controller.create_card("Амулет стойкости", card_type="item")
            modifier = Modifier("constitution", operand=2)
            service.update_card_fields(
                item.id, {"modifiers": (modifier,), "weight": 1, "cost": 80, "rarity": "Необычный"}
            )
            inv = controller.tables_service.get_table(service.get_actor(ref).inventory_id)
            controller.tables_service.edit_table(inv.id, rows=(inv.new_row(),))
            inv = controller.tables_service.get_table(inv.id)
            controller.tables_service.set_cell(inv.id, inv.rows[0].id, inv.columns[0].id, item.id)
            active = next(c for c in inv.columns if c.key == "active")
            controller.tables_service.set_cell(inv.id, inv.rows[0].id, active.id, True, parsed=True)
            equipment_cards = []
            for equipment_kind, category, armor_ac, title in (
                ("armor", "medium", 14, "Кираса"),
                ("shield", None, None, "Щит"),
            ):
                equipment = controller.create_card(title, card_type="item")
                equipment_cards.append(equipment)
                service.update_card_fields(
                    equipment.id,
                    {
                        "equipment_kind": equipment_kind,
                        "armor_category": category,
                        "armor_ac": armor_ac,
                        "weight": 0,
                    },
                )
                inventory = controller.tables_service.get_table(inv.id)
                row = inventory.new_row()
                controller.tables_service.edit_table(inv.id, rows=(*inventory.rows, row))
                item_column = next(c for c in inventory.columns if c.key == "item")
                controller.tables_service.set_cell(inv.id, row.id, item_column.id, equipment.id)
                controller.actions.set_inventory_activity(inv.id, row.id, True)
            controller.card_views.open_game_sheet(card.id, ref.actor_id)
            capture(window, "01-character-workspace")
            binding = controller.card_views.game_bindings[card.id]
            binding.open_armor()
            capture(binding.armor_dialog, "12-ac-details")
            binding.armor_dialog.close()
            dock = controller.card_views.open_game_sheet(card.id, ref.actor_id)
            dock.dock.setFloating()
            floating = dock.dock.floatingDockContainer()
            for width, name in (
                (1040, "02-character-wide"),
                (660, "03-character-medium"),
                (400, "04-character-narrow"),
            ):
                floating.resize(width, 1000)
                capture(dock.widget(), name)
            floating.resize(1040, 1000)
            controller.card_views.game_bindings[card.id].select_actor(None)
            capture(dock.widget(), "05-base-card")
            chest = controller.create_card("Сундук экспедиции", card_type="object")
            service.update_card_fields(
                chest.id, {"hp_max": 25, "ac": 12, "ac_mode": "manual", "speed": 0}
            )
            obj = controller.card_views.open_game_sheet(chest.id)
            obj.dock.setFloating()
            obj.dock.floatingDockContainer().resize(680, 800)
            capture(obj.widget(), "06-object")
            item_dock = controller.card_views.open_game_sheet(item.id)
            item_dock.dock.setFloating()
            item_dock.dock.floatingDockContainer().resize(700, 800)
            capture(item_dock.widget(), "07-item-list")
            for index, equipment_card in enumerate(equipment_cards, 13):
                equipment_dock = controller.card_views.open_game_sheet(equipment_card.id)
                equipment_dock.dock.setFloating()
                equipment_dock.dock.floatingDockContainer().resize(700, 800)
                capture(equipment_dock.widget(), f"{index}-equipment-item")
            inventory_dock = controller.tables.open_table(inv.id)
            inventory_dock.dock.setFloating()
            inventory_dock.dock.floatingDockContainer().resize(920, 620)
            capture(inventory_dock.widget(), "15-equipped-inventory")
            dialog = ModifierDialog(
                {
                    "id": modifier.id,
                    "target": "constitution",
                    "operation": "add",
                    "operand": 2,
                    "group": "",
                    "policy": "sum",
                    "priority": 0,
                    "condition": "",
                },
                window,
            )
            dialog.show()
            capture(dialog, "08-item-form")
            dialog.reject()
            rules = controller.open_rules()
            rules.select_formula("constitution_mod")
            rules.example_controls["constitution"].setText("16")
            rules.test_example()
            capture(rules, "09-rules-example")
            rules.resize(640, 480)
            capture(rules, "09b-rules-small")
            rules.resize(940, 660)
            rules.select_formula("hp_max")
            rules.advanced_toggle.setChecked(True)
            rules.expression.setPlainText("20")
            rules.check_project()
            capture(rules, "10-rules-preview")
            rules.close_for_project()
            for key in tuple(controller.window_manager.window_keys()):
                controller.window_manager.close_window(key)
            source = root / "map.png"
            image = QImage(800, 600, QImage.Format.Format_RGB32)
            image.fill(0xFF303838)
            assert image.save(str(source))
            asset = project.store.import_asset(source)
            project.assets[asset.id] = asset
            document = controller.maps_service.create_map("Походная карта", asset.id)
            token = controller.maps_service.add_token(document.id, card.id, 250, 200)
            controller.maps.open_map(document.id)
            settle(1)
            controller.maps.focus_token(document.id, token.id)
            capture(window, "11-map-inspector")
            from PySide6.QtCore import QPointF

            viewer = controller.maps.open_map(document.id).widget()
            viewer.fog_tools.show()
            viewer.fog_tools.set_mode("polygon")
            viewer.fog_tools.points = [(120, 120), (450, 140), (400, 350)]
            viewer.fog_tools._preview(QPointF(121, 121))
            capture(viewer, "16-polygon-snap")
            viewer.tool_state.activate("select")
            from PySide6.QtCore import QRectF
            from PySide6.QtGui import QPainterPath

            from lodandsy.domain.map_document import MapPortal, MapShape

            controller.maps_service.edit_map(
                document.id,
                grid=replace(controller.maps_service.get_map(document.id).grid, feet_per_cell=5),
            )
            for value in (
                MapShape("circle", ((70, 0),), x=200, y=170, name="Радиус", color="#73d6b2"),
                MapShape(
                    "cone", ((180, 0),), x=400, y=320, rotation=-30, name="Конус", color="#f5b764"
                ),
                MapShape(
                    "rectangle",
                    ((0, 0), (150, 0), (150, 90), (0, 90)),
                    x=100,
                    y=360,
                    name="Граница",
                    color="#b6a4ff",
                ),
            ):
                controller.maps_service.put_vector(document.id, value)
            target = controller.maps_service.create_map("Нижний уровень", asset.id)
            controller.maps_service.put_vector(document.id, MapPortal(target.id, 620, 420))
            fog = QPainterPath()
            fog.addRect(QRectF(0, 0, 800, 600))
            controller.maps_service.edit_fog(document.id, fog)
            viewer.tool_state.activate("select")
            viewer.vector_tools.select(controller.maps_service.get_map(document.id).shapes[0])
            capture(window, "17-m5-gm-shapes")
            capture(window, "24-m55-unified-wide")
            from lodandsy.ui.map_settings_dialogs import MapGridDialog, MapPortalDialog

            grid_dialog = MapGridDialog(
                controller.maps_service.get_map(document.id).grid,
                window,
                measurement_mode=viewer.view.measurement_mode,
            )
            grid_dialog.show()
            capture(grid_dialog, "25-m55-grid-measurement")
            grid_dialog.close()
            viewer.tool_state.activate("fog_hide")
            capture(viewer, "26-m55-fog-brush")
            viewer.tool_state.activate("fog_polygon")
            viewer.fog_tools.points = [(100, 100), (300, 120), (260, 300)]
            viewer.fog_tools._preview(QPointF(101, 101))
            capture(viewer, "27-m55-fog-polygon")
            viewer.tool_state.activate("select")
            menu = viewer.tools.actions["shape"].menu()
            menu.popup(viewer.tools.sidebar.mapToGlobal(viewer.tools.sidebar.rect().topRight()))
            capture(menu, "28-m55-shape-menu")
            capture(window, "34-m55-shape-menu-gap")
            menu.close()
            selection_menu = viewer.tools.actions["select"].menu()
            selection_menu.popup(
                viewer.tools.sidebar.mapToGlobal(viewer.tools.sidebar.rect().topRight())
            )
            capture(window, "35-m55-selection-menu")
            selection_menu.close()
            viewer.tool_state.activate("portal")
            capture(viewer, "29-m55-portal")
            portal = controller.maps_service.get_map(document.id).portals[0]
            portal_dialog = MapPortalDialog(
                replace(portal, label="Нижний уровень", hide_label=True), window
            )
            portal_dialog.show()
            capture(portal_dialog, "36-m55-portal-hide-label-dialog")
            portal_dialog.close()
            controller.maps_service.put_vector(
                document.id, replace(portal, label="Нижний уровень", hide_label=True)
            )
            capture(viewer, "37-m55-hidden-portal-label")
            viewer.tool_state.activate("select")
            player = controller.maps.open_presentation(document.id)
            settle(1)
            capture(player, "18-m5-player-shapes-over-fog")
            controller.maps._measurement(
                document.id, (token.id, (250, 200), (450, 320)), viewer.view.measurement_mode
            )
            capture(viewer, "19-m5-gm-distance")
            capture(player, "20-m5-player-hidden-distance")
            controller.maps._measurement(document.id, None, "grid")
            map_window = controller.maps.open_map(document.id)
            map_window.dock.setFloating()
            map_floating = map_window.dock.floatingDockContainer()
            map_floating.show()
            map_floating.resize(650, 650)
            capture(viewer, "23-m5-map-narrow")
            map_floating.resize(320, 300)
            capture(viewer, "30-m55-overflow")
            from PySide6.QtWidgets import QToolButton

            extension = viewer.tools.sidebar.findChild(QToolButton, "qt_toolbar_ext_button")
            overflow = extension.menu()
            overflow.popup(extension.mapToGlobal(extension.rect().bottomRight()))
            capture(overflow, "31-m55-overflow-menu")
            overflow.close()
            viewer.tool_state.activate("fog_hide")
            capture(viewer, "32-m55-narrow-fog")
            viewer.tool_state.activate("select")
            capture(viewer, "33-m55-narrow-select")
            viewer.tool_state.activate("select")
            map_floating.resize(650, 650)
            portrait = QImage(1024, 400, QImage.Format.Format_RGB32)
            portrait.fill(0xFF416E8C)
            portrait_source = root / "portrait.png"
            assert portrait.save(str(portrait_source))
            portrait_asset = project.store.import_asset(portrait_source)
            project.assets[portrait_asset.id] = portrait_asset
            controller.maps_service.edit_token(
                document.id, token.id, image_override=portrait_asset.id
            )
            # Explicitly approve disclosure only in this disposable synthetic world.
            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QMessageBox

            def approve():
                for dialog in app.topLevelWidgets():
                    if isinstance(dialog, QMessageBox):
                        dialog.button(QMessageBox.StandardButton.Yes).click()

            QTimer.singleShot(50, approve)
            controller.maps._token_action(document.id, token.id, "portrait")
            settle(1)
            assert len(controller.maps._portrait_views) == 2
            capture(viewer, "21-m5-gm-original-image")
            capture(player, "22-m5-player-original-image")
            controller.maps._close_portrait()
            player.close()
            assert project.save_current()
            (args.output / "evidence.json").write_text(
                json.dumps(
                    {
                        "platform": app.platformName(),
                        "device_pixel_ratio": window.devicePixelRatioF(),
                        "capture": "QWidget.grab: production Qt views; not compositor capture",
                        "isolated_world_and_catalogue": True,
                        "manual_physical_acceptance": False,
                        "card_actor_hp": service.get_actor(ref).value("hp_current"),
                        "effective_hp_max": service.effective(ref).get("hp_max").value,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        finally:
            window.close_guard = None
            controller.shutdown_features()
            project.saver.shutdown()
            if project.store:
                project.store.close()
            window.close()
            app.processEvents()


if __name__ == "__main__":
    main()
