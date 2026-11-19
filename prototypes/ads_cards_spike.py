"""Historical W2 preflight, now exercising the accepted production adapter.

Run with the build venv containing Qt ADS. Uses the same SQLite/Cards workflows.
--self-test --report <path> exercises real Card Editor and reports assertions.
The owner passed manual Windows acceptance before production migration.
"""

import argparse
import base64
import importlib
import json
import sys
import tempfile
import traceback
from pathlib import Path

from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.ui.app_shell import AppShell

# Load Qt's Python modules before the native extension, including in a frozen process.
ads = importlib.import_module("PySide6QtAds")


def make_window():
    window = AppShell()
    controller = AppController(window)
    manager = controller.window_manager
    project = ProjectController(controller)
    menu = window.menuBar().addMenu("Preflight")

    def save_layout():
        filename, _ = QFileDialog.getSaveFileName(window, "Save test layout", "", "Layout (*)")
        if filename:
            Path(filename).write_text(
                json.dumps(capture_layout(window, controller, manager)), encoding="utf-8"
            )

    def restore_layout():
        filename, _ = QFileDialog.getOpenFileName(window, "Restore test layout", "", "Layout (*)")
        if filename:
            try:
                data = Path(filename).read_text(encoding="utf-8")
                if len(data) > 5_000_000:
                    raise ValueError("Test layout is too large")
                restore_layout_data(window, controller, manager, json.loads(data))
            except (OSError, ValueError) as error:
                QMessageBox.warning(window, "Layout", str(error))

    menu.addAction("Save test layout", save_layout)
    menu.addAction("Restore test layout", restore_layout)
    return window, controller, manager, project


def capture_layout(window, controller, manager):
    return {
        "version": 1,
        "open_cards": list(controller.card_views.editors),
        "ads": base64.b64encode(bytes(manager.workspace.saveState(1))).decode("ascii"),
        "geometry": base64.b64encode(bytes(window.saveGeometry())).decode("ascii"),
    }


def restore_layout_data(window, controller, manager, data):
    if (
        not isinstance(data, dict)
        or data.get("version") != 1
        or not isinstance(data.get("open_cards"), list)
        or not all(isinstance(card_id, str) for card_id in data["open_cards"])
        or not isinstance(data.get("ads"), str)
        or not isinstance(data.get("geometry"), str)
    ):
        raise ValueError("Unsupported test layout")
    state = base64.b64decode(data["ads"], validate=True)
    geometry = base64.b64decode(data["geometry"], validate=True)
    for card_id in data["open_cards"]:
        controller.cards.get(card_id)
    for card_id in data["open_cards"]:
        controller.open_card_editor(card_id)
    window.restoreGeometry(QByteArray(geometry))
    if not manager.workspace.restoreState(QByteArray(state), 1):
        raise ValueError("The test layout could not be restored")
    QApplication.processEvents()
    screens = QApplication.screens()
    for floating in [window, *manager.workspace.floatingWidgets()]:
        maximized = floating.isMaximized()
        rect = floating.normalGeometry() if maximized else floating.geometry()
        screen = next(
            (s for s in screens if s.availableGeometry().contains(rect.center())),
            QApplication.primaryScreen(),
        )
        area = screen.availableGeometry()
        width, height = min(rect.width(), area.width()), min(rect.height(), area.height())
        x = max(area.left(), min(rect.x(), area.right() - width + 1))
        y = max(area.top(), min(rect.y(), area.bottom() - height + 1))
        if maximized:
            floating.showNormal()
        floating.setGeometry(x, y, width, height)
        if maximized:
            floating.showMaximized()


def self_test(app, window, controller, manager, project):
    a, b = controller.create_card("Card A"), controller.create_card("Card B")
    first, second = controller.open_card_editor(a.id), controller.open_card_editor(b.id)
    first.widget().text_edit.insertPlainText("A edited")
    second.widget().text_edit.insertPlainText("B edited")
    app.processEvents()
    assert first.widget().card_id == a.id and second.widget().card_id == b.id
    assert controller.open_card_editor(a.id) is first
    for area in [
        ads.RightDockWidgetArea,
        ads.BottomDockWidgetArea,
        ads.LeftDockWidgetArea,
        ads.TopDockWidgetArea,
        ads.CenterDockWidgetArea,
    ]:
        manager.workspace.addDockWidget(area, second.dock, first.dock.dockAreaWidget())
        app.processEvents()
        assert controller.cards.get(a.id).content == "A edited"
        assert controller.cards.get(b.id).content == "B edited"
    second.dock.setFloating()
    app.processEvents()
    floating = second.dock.floatingDockContainer()
    assert floating is not None and floating.isWindow()
    floating.showMaximized()
    app.processEvents()
    assert floating.isMaximized()
    floating.showNormal()
    floating.move(100_000, 100_000)
    outside_layout = capture_layout(window, controller, manager)
    restore_layout_data(window, controller, manager, outside_layout)
    assert any(
        screen.availableGeometry().contains(floating.geometry().topLeft())
        for screen in app.screens()
    )
    manager.workspace.addDockWidget(
        ads.RightDockWidgetArea, second.dock, first.dock.dockAreaWidget()
    )
    saved = manager.workspace.saveState(1)
    assert manager.workspace.restoreState(saved, 1)
    app.processEvents()
    assert controller.cards.get(a.id).content == "A edited"
    assert controller.cards.get(b.id).content == "B edited"
    layout = capture_layout(window, controller, manager)
    for key in manager.window_keys():
        manager.close_window(key)
    app.processEvents()
    restore_layout_data(window, controller, manager, layout)
    assert set(controller.card_views.editors) == {a.id, b.id}
    assert controller.card_views.editors[b.id].text_edit.toPlainText() == "B edited"
    assert project.save_current()
    saved_cards = project.store.load().cards
    assert any(card.id == b.id and card.content == "B edited" for card in saved_cards)
    assert controller.window.tree_host.isMovable() is False
    assert controller.window.inspector_host.isMovable() is False
    assert manager.close_window(first.key)
    app.processEvents()
    reopened = controller.open_card_editor(a.id)
    assert reopened is not first
    assert reopened.widget().text_edit.toPlainText() == "A edited"
    reopened.widget().text_edit.undo()
    assert controller.cards.get(a.id).content == ""
    assert controller.cards.get(b.id).content == "B edited"
    return {
        "cards_independent": True,
        "programmatic_docking_directions": True,
        "float_maximize_redock": True,
        "layout_roundtrip": True,
        "fixed_panels": True,
        "reopen_undo": True,
        "sqlite_save": True,
        "offscreen_restore_clamped": True,
        "frozen": bool(getattr(sys, "frozen", False)),
        "runtime_prefix": sys.prefix,
        "platform": app.platformName(),
        "screens": [
            {
                "width": s.geometry().width(),
                "height": s.geometry().height(),
                "dpr": s.devicePixelRatio(),
                "dpi": s.logicalDotsPerInch(),
            }
            for s in app.screens()
        ],
        "manual_acceptance": "not performed",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    app = QApplication([])
    window, controller, manager, project = make_window()
    window.show()
    if not args.self_test:
        return app.exec()
    try:
        with tempfile.TemporaryDirectory(prefix="lodandsy-w2-selftest-") as temporary:
            root = Path(temporary).resolve()
            assert root.is_relative_to(Path(tempfile.gettempdir()).resolve())
            project.create_project(root / "world")
            try:
                result = self_test(app, window, controller, manager, project)
            finally:
                project.saver.shutdown()
                controller.shutdown_features()
                project.store.close()
                window.close_guard = None
        status = 0
    except Exception:
        result = {"error": traceback.format_exc()}
        status = 1
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    elif sys.stdout is not None:
        print(json.dumps(result))
    window.close()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
