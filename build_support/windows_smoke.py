"""Run the actual application workflows in a disposable project, including frozen Qt."""

import argparse
import json
import sys
import tempfile
import time
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

import PySide6
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.application.workspace_state import capture_workspace
from lodandsy.domain.map_document import MapGrid
from lodandsy.domain.table_document import ColumnDefinition, RowRecord
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.theme import apply_theme


def wait(app, predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise RuntimeError("Smoke workflow timed out")
        app.processEvents()
        time.sleep(0.005)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--large-map-image", type=Path)
    args = parser.parse_args()
    app = QApplication([])
    apply_theme(app)
    window = AppShell()
    controller = AppController(window)
    project = ProjectController(controller)
    window.show()
    try:
        with (
            tempfile.TemporaryDirectory(prefix="lodandsy-mvp-smoke-") as temporary,
            ExitStack() as cleanup,
        ):
            cleanup.callback(lambda: project.store.close() if project.store else None)
            cleanup.callback(controller.modules.shutdown)
            cleanup.callback(controller.card_images.shutdown)
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
            controller.card_images.insert(first.widget(), source, "Изображение города")
            wait(app, lambda: not controller.card_images.importing)
            assert "assets/" in controller.cards.get(a.id).content
            controller.card_images.portrait(second.widget(), source)
            wait(app, lambda: not controller.card_images.importing)
            assert controller.cards.get(b.id).portrait.asset_id in project.assets
            portrait = controller.cards.get(b.id).portrait
            second.widget().portrait_panel.changed.emit(
                replace(portrait, crop=(0.2, 0.1, 0.4, 0.8))
            )
            notes = controller.session.add_section(a.id, "Путевые заметки")
            first.widget().select_section(notes.id)
            first.widget().text_edit.insertPlainText("Независимый раздел")
            inventory = next(
                s for s in controller.cards.get(b.id).sections if s.purpose == "inventory"
            )
            inventory_table = controller.session.section_table(b.id, inventory.id)
            assert controller.session.section_table(b.id, inventory.id).id == inventory_table.id
            second.widget().select_section(inventory.id)
            progress = []
            controller.modules.import_progress.connect(progress.append)
            controller.modules.import_map(args.large_map_image or source, "Область")
            wait(app, lambda: not controller.modules.importing, timeout=120)
            assert any(0 < value < 100 for value in progress), "Worker progress pipe missing"
            document = next(iter(controller.modules.session.maps.values()))
            controller.session.update_entity(document.id, parent_id=b.id)
            map_widget = controller.modules.open_map(document.id).widget()
            wait(app, lambda: map_widget.view._background is not None, timeout=120)
            grid = MapGrid(True, 50, 10, 10, 0.5)
            controller.modules.session.edit_map(document.id, grid=grid)
            token = controller.modules.session.add_token(document.id, a.id, 120, 130)
            item_token = controller.modules.session.add_token(
                document.id, b.id, 220, 230, kind_override="item", cells_w=2, cells_h=2
            )
            assert item_token.card_id == b.id
            controller.session.update_card_fields(a.id, {"hp": 0, "summary": "Canonical summary"})
            assert map_widget.view._tokens[0].presentation.summary == "Canonical summary · HP: 0"
            layer = controller.modules.session.add_layer(document.id, "Decor")
            other_layer = controller.modules.session.add_layer(document.id, "Upper")
            controller.modules.session.add_object(
                document.id, layer.id, document.asset_id, 10, 20, 100, 80
            )
            controller.modules.session.add_object(
                document.id, other_layer.id, document.asset_id, 110, 120, 100, 80
            )
            map_editor = controller.modules.open_map_editor(document.id).widget()
            assert map_editor is not map_widget and len(map_editor.view._objects) == 2
            controller.modules.session.edit_layer(document.id, other_layer.id, visible=False)
            controller.modules.session.move_token(document.id, token.id, 190, 190)
            assert controller.modules.session.get_map(document.id).tokens[0].x == 190
            controller.modules.session.undo_stack(document.id).undo()
            assert controller.modules.session.get_map(document.id).tokens[0].x == token.x
            table = controller.modules.session.create_table("Встречи")
            controller.session.update_entity(table.id, parent_id=document.id)
            columns = (
                ColumnDefinition("Событие"),
                ColumnDefinition("Количество", "number", 1),
                ColumnDefinition("Есть", "bool", 2),
            )
            controller.modules.session.edit_table(
                table.id,
                columns=columns,
                rows=(
                    RowRecord(
                        0, ((columns[0].id, "Купец"), (columns[1].id, 0), (columns[2].id, False))
                    ),
                    RowRecord(1),
                ),
            )
            table_widget = controller.modules.open_table(table.id).widget()
            assert table_widget.model.setData(table_widget.model.index(0, 0), "Дракон")
            table_widget.table.selectRow(0)
            table_widget.copy_selection()
            assert QApplication.clipboard().text() == "Дракон\t0\tfalse"
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
            dice = controller.modules.open_dice().widget()
            dice.counts[20].setValue(0)
            dice.counts[6].setValue(3)
            dice.counts[100].setValue(1)
            dice.modifier.setValue(-2)
            dice.throw()
            assert " = " in dice.result.toPlainText()
            assert "d100:" in dice.result.toPlainText()
            assert len(controller.window_manager.window_keys()) == 6
            second.dock.setFloating()
            app.processEvents()
            assert second.dock.floatingDockContainer().isWindow()
            # Explicit synthetic MOW fixture; the real supplied sample is covered by pytest.
            from uuid import uuid4

            from lodandsy.application.mow_import import (
                apply_import,
                inspect_source,
                prepare_import,
            )

            mow_source = root / "MOW-synthetic.md"
            mow_source.write_text(
                f"---\nid: {uuid4()}\nschemaVersion: 1\ntype: folder\n"
                "tags: [card, folder]\naliases: []\n---\n"
                '<h1>Импорт MOW</h1><div class="entity-main">'
                '<div class="rich-text-field"><b>Содержимое</b>'
                "<select><option>runtime</option></select></div></div>",
                encoding="utf-8",
            )
            imported = prepare_import(
                inspect_source(mow_source),
                project.store,
                controller.cards.all(),
                tuple(project.assets.values()),
            )
            apply_import(controller.session, imported)
            assert imported.cards[0].card_type == "folder"
            assert "runtime" not in imported.cards[0].content
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
            restored_map = controller.modules.open_map(document.id).widget()
            wait(app, lambda: restored_map.view._background is not None, timeout=120)
            project.open_project(root / "Мир с кириллицей")
            reopened_map = controller.modules.open_map(document.id).widget()
            wait(app, lambda: reopened_map.view._background is not None, timeout=120)
            wait(app, lambda: len(controller.window_manager.window_keys()) == 6)
            assert project.store.load() == expected
            controller.delete_card(a.id)
            assert len(controller.modules.session.get_map(document.id).tokens) == 1
            assert controller.cards.get(b.id)
            assert project.save_current()
            result = {
                "passed": True,
                "frozen": bool(getattr(sys, "frozen", False)),
                "python": sys.version,
                "qt": PySide6.__version__,
                "platform": app.platformName(),
                "cards_maps_tools_sqlite": True,
                "backup_restore": True,
                "independent_windows": True,
                "layout_reopen": True,
                "card_placements_cascade_atomically": True,
                "layers_raster_objects": True,
                "canonical_card_fields": True,
                "mow_synthetic_import": True,
                "unicode_paths": True,
                "uuid_sections_child_inventory_crop": True,
                "independent_map_editor_free_tokens": True,
                "typed_table_and_nonblocking_drafts": True,
                "application_dice_tool": True,
                "mixed_entity_hierarchy": True,
                "large_map_supplied": bool(args.large_map_image),
                "manual_acceptance": "not performed by this automated smoke",
            }
            args.report.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    finally:
        window.close_guard = None
        window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
