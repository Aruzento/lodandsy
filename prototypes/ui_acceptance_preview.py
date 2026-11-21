"""Render real production Qt views in an isolated disposable world for visual review."""

import argparse
import json
import tempfile
import time
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
                    "armor_type": "medium",
                    "armor_base": 14,
                    "shield": True,
                    "speed_mode": "auto",
                    "class_or_role": "Воин",
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
            controller.card_views.open_game_sheet(card.id, ref.actor_id)
            capture(window, "01-character-workspace")
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
            service.update_card_fields(chest.id, {"hp_max": 25, "ac": 12, "speed": 0})
            obj = controller.card_views.open_game_sheet(chest.id)
            obj.dock.setFloating()
            obj.dock.floatingDockContainer().resize(680, 800)
            capture(obj.widget(), "06-object")
            item_dock = controller.card_views.open_game_sheet(item.id)
            item_dock.dock.setFloating()
            item_dock.dock.floatingDockContainer().resize(700, 800)
            capture(item_dock.widget(), "07-item-list")
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
