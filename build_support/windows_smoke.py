"""Run the actual application workflows in a disposable project, including frozen Qt."""

import argparse
import json
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

import PySide6
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.application.workspace_state import capture_workspace
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.theme import apply_theme


def wait(app, predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise RuntimeError("Smoke workflow timed out")
        app.processEvents()
        time.sleep(.005)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    app = QApplication([])
    apply_theme(app)
    window = AppShell()
    controller = AppController(window)
    project = ProjectController(controller)
    window.show()
    try:
        with (tempfile.TemporaryDirectory(prefix="lodandsy-mvp-smoke-") as temporary,
              ExitStack() as cleanup):
            cleanup.callback(lambda: project.store.close() if project.store else None)
            cleanup.callback(controller.modules.shutdown)
            cleanup.callback(project.saver.shutdown)
            cleanup.callback(setattr, window, "close_guard", None)
            root = Path(temporary).resolve()
            project.create_project(root / "Мир с кириллицей")
            a = controller.create_card("Город")
            b = controller.create_card("Таверна", a.id)
            first = controller.open_card_editor(a.id)
            second = controller.open_card_editor(b.id)
            first.widget().text_edit.insertPlainText("# Город\n\n" + "История " * 10)
            second.widget().text_edit.insertPlainText(f"[Дом](lodandsy://card/{a.id})")
            first.widget().mode_combo.setCurrentIndex(2)
            image = QImage(1200, 800, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.darkGreen)
            source = root / "Карта.png"
            assert image.save(str(source))
            controller.modules.import_map(source, "Область")
            wait(app, lambda: not controller.modules.importing)
            document = next(iter(controller.modules.session.maps.values()))
            marker = controller.modules.session.add_pin(document.id, "Город", .3, .4, a.id)
            controller.modules.session.add_pin(document.id, "Таверна", .7, .6, a.id)
            controller.modules.session.edit_pin(document.id, marker.id, x=.5)
            controller.modules.session.undo_stack(document.id).undo()
            assert controller.modules.session.get_map(document.id).pins[0].x == .3
            table = controller.modules.session.create_table("Встречи")
            controller.modules.session.edit_table(table.id, rows=("Купец", "Дракон"))
            controller.modules.open_table(table.id)
            dice = controller.modules.open_dice().widget()
            dice.expression.setText("3d6-2")
            dice.throw()
            assert " = " in dice.result.toPlainText()
            assert len(controller.window_manager.window_keys()) == 5
            second.dock.setFloating()
            app.processEvents()
            assert second.dock.floatingDockContainer().isWindow()
            assert project.save_current()
            expected = project.store.load()
            project._save_ui_state()
            assert capture_workspace(controller)["documents"]
            backup = root / "backup.lodbackup"
            project.store.backup(backup)
            restored = SQLiteProjectStore.restore(backup, root / "Восстановлено")
            assert restored.load() == expected
            restored.close()
            project.open_project(root / "Восстановлено")
            project.open_project(root / "Мир с кириллицей")
            wait(app, lambda: len(controller.window_manager.window_keys()) == 5)
            assert project.store.load() == expected
            controller.delete_card(a.id)
            assert len(controller.modules.session.get_map(document.id).pins) == 2
            assert project.save_current()
            result = {
                "passed": True, "frozen": bool(getattr(sys, "frozen", False)),
                "python": sys.version, "qt": PySide6.__version__, "platform": app.platformName(),
                "cards_maps_tools_sqlite": True, "backup_restore": True,
                "independent_windows": True, "layout_reopen": True,
                "broken_markers_survive": True, "unicode_paths": True,
                "manual_acceptance": "not performed by this automated smoke",
            }
            args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    finally:
        window.close_guard = None
        window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
