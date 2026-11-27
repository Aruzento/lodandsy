"""Take native screenshots of every card icon in a disposable project."""

import argparse
import json
import tempfile
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QSettings, Qt
from PySide6.QtGui import QImage, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QApplication, QDialog

from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.application.project_history import ProjectHistory
from lodandsy.domain.card_schema import CARD_TYPES
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.theme import ICON_SIZE, apply_theme


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    application = QApplication([])
    apply_theme(application)
    with tempfile.TemporaryDirectory(prefix="lodandsy-tree-icons-") as temporary:
        root = Path(temporary)
        window = AppShell()
        app = AppController(window)
        projects = ProjectController(
            app, ProjectHistory(QSettings(str(root / "history.ini"), QSettings.Format.IniFormat))
        )
        other = QDialog()
        try:
            projects.create_project(root / "Иконки карточек")
            folder = app.create_card("Папка игровых материалов", card_type="folder")
            cards = {
                kind: app.create_card(definition.title, folder.id, card_type=kind)
                for kind, definition in CARD_TYPES.items() if kind != "folder"
            }
            image = QImage(16, 16, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.darkGray)
            source = root / "map.png"
            assert image.save(str(source))
            asset = projects.store.import_asset(source)
            projects.assets[asset.id] = asset
            app.maps_service.create_map("Карта гавани", asset.id)
            app.tables_service.create_table("Таблица находок")
            assert projects.save_current()

            panel = window.tree_panel
            tree, model = panel.tree_view, panel.tree_model
            available = window.screen().availableGeometry()
            window.resize(min(1040, available.width() - 40), min(660, available.height() - 50))
            window.show()
            window.resizeDocks([panel], [252], Qt.Orientation.Horizontal)
            tree.expand(model.index_for_node(f"card:{folder.id}"))
            character = f"card:{cards['character'].id}"
            panel.select_node(character)
            window.activateWindow()
            tree.setFocus()
            QTest.qWait(180)
            assert window.isActiveWindow()
            hovered = model.index_for_node(f"card:{cards['item'].id}")
            point = tree.visualRect(hovered).center()
            QApplication.sendEvent(tree.viewport(), QMouseEvent(
                QEvent.Type.MouseMove, QPointF(point),
                QPointF(tree.viewport().mapToGlobal(point)),
                Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            ))
            assert panel.inline_actions.index == hovered
            QTest.qWait(180)
            assert panel.inline_actions.index == hovered
            assert len(model.node_keys()) == len(CARD_TYPES) + 2
            assert tree.iconSize().width() == ICON_SIZE
            assert panel.grab().save(str(args.output / "active.png"))

            def visible_keys():
                return {
                    key for key in model.node_keys()
                    if tree.viewport().rect().contains(tree.visualRect(model.index_for_node(key)))
                }

            visible = visible_keys()
            scrolled = len(visible) < len(model.node_keys())
            if scrolled:
                scrollbar = tree.verticalScrollBar()
                initial = scrollbar.value()
                last = model.index_for_node(model.node_keys()[-1])
                tree.scrollTo(last, QAbstractItemView.ScrollHint.PositionAtBottom)
                QTest.qWait(180)
                visible |= visible_keys()
                assert panel.grab().save(str(args.output / "active-scrolled.png"))
                scrollbar.setValue(initial)
            assert visible == set(model.node_keys())

            other.setWindowTitle("Проверка деактивации")
            other.show()
            other.activateWindow()
            QTest.qWait(180)
            assert not window.isActiveWindow()
            assert panel.current_node_key() == character
            assert panel.grab().save(str(args.output / "inactive.png"))
            report = {
                "platform": application.platformName(),
                "device_pixel_ratio": window.devicePixelRatioF(),
                "logical_icon_px": tree.iconSize().width(),
                "card_types": list(CARD_TYPES),
                "selected_type": "character",
                "hovered_type_in_active_capture": "item",
                "inactive_window_verified": True,
                "scrolled_capture": scrolled,
            }
            (args.output / "review.json").write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8",
            )
            print(report)
        finally:
            other.close()
            window.close_guard = None
            app.shutdown_features()
            projects.saver.shutdown()
            if projects.store is not None:
                projects.store.close()
            window.close()


if __name__ == "__main__":
    main()
