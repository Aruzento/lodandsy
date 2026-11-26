"""Capture matched native views for the UI design review in a disposable world."""

import argparse
import json
import tempfile
from pathlib import Path

from PySide6.QtCore import QPoint, QSettings
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.application.project_history import ProjectHistory
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.project_chooser import ProjectChooser
from lodandsy.ui.theme import apply_theme


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    apply_theme(app)
    observations = {}

    def capture(widget, name):
        QTest.qWait(100)
        assert widget.grab().save(str(args.output / f"{name}.png"))

    with tempfile.TemporaryDirectory(prefix="lodandsy-design-") as temporary:
        root = Path(temporary)
        shell = AppShell()
        controller = AppController(shell)
        history = ProjectHistory(QSettings(str(root / "mru.ini"), QSettings.Format.IniFormat))
        project = ProjectController(controller, history)
        try:
            welcome = ProjectChooser([], shell, welcome=True)
            welcome.show()
            capture(welcome, "welcome")
            welcome.close()
            project.create_project(root / "Северная гавань")
            shell.resize(1140, 780)
            shell.show()
            table = controller.tables_service.create_table("Дорожный журнал")
            controller.tables_service.edit_table(table.id, rows=(table.new_row(),))
            doc = controller.tables.open_table(table.id)
            capture(shell, "table-docked")
            table_view = doc.widget().table
            header_buttons = [h.plus for h in (table_view.horizontalHeader(),
                                               table_view.verticalHeader())]
            assert header_buttons[0].size() == header_buttons[1].size()
            observations["append_button_logical_px"] = header_buttons[0].width()
            dice = controller.dice.open()
            view = dice.widget()
            view.counts[20].setValue(1)
            view.counts[6].setValue(2)
            view.throw()
            capture(shell, "dice-docked")
            dice.dock.setFloating()
            dice.dock.floatingDockContainer().resize(420, 630)
            capture(view, "dice-floating")
            assert view.roll.isVisible()
            assert view.roll.mapTo(view, view.roll.rect().topRight()).x() < view.width()
            observations["dice_floating_logical_width"] = view.width()
            controller.window_manager.close_window("tool:dice")
            settings = controller.open_economy().window()
            capture(settings, "settings")
            currency = settings.economy.table
            assert currency.rowCount() == 5
            visible_rows = [currency.visualItemRect(currency.item(row, 0)) for row in range(5)]
            assert all(currency.viewport().rect().contains(rect) for rect in visible_rows)
            observations["settings_standard_rows_visible"] = len(visible_rows)
            observations["settings_logical_size"] = [settings.width(), settings.height()]
            settings.close()
            image = QImage(960, 640, QImage.Format.Format_RGB32)
            image.fill(0xFF343C40)
            path = root / "map.png"
            assert image.save(str(path))
            asset = project.store.import_asset(path)
            project.assets[asset.id] = asset
            map_document = controller.maps_service.create_map("Северная гавань", asset.id)
            controller.maps.open_map_editor(map_document.id)
            capture(shell, "map-editor")
            controller.window_manager.close_window(doc.key)
            viewer = controller.maps.open_map(map_document.id).widget()
            menu = viewer.tools.actions["shape"].menu()
            observations["map_menu_bounds"] = []
            for index, screen in enumerate(app.screens()):
                bounds = screen.availableGeometry()
                shell.windowHandle().setScreen(screen)
                shell.resize(min(900, bounds.width() - 20), min(700, bounds.height() - 32))
                shell.move(bounds.bottomRight() - shell.rect().bottomRight() - QPoint(10, 16))
                QTest.qWait(100)
                button = menu.parentWidget()
                menu.popup(button.mapToGlobal(button.rect().topRight()))
                capture(menu, f"map-menu-screen-{index + 1}")
                assert button.screen() == screen
                assert bounds.contains(menu.geometry())
                observations["map_menu_bounds"].append([
                    bounds.x(), bounds.y(), bounds.width(), bounds.height(),
                ])
                menu.close()
        finally:
            shell.close_guard = None
            controller.shutdown_features()
            project.saver.shutdown()
            if project.store:
                project.store.close()
            shell.close()
    if args.report:
        screen = app.primaryScreen()
        observations.update({
            "platform": app.platformName(),
            "device_pixel_ratio": screen.devicePixelRatio(),
            "screen_count": len(app.screens()),
            "logical_screen_size": [screen.size().width(), screen.size().height()],
        })
        args.report.write_text(json.dumps(observations, indent=2), encoding="utf-8")
        print(observations)


if __name__ == "__main__":
    main()
