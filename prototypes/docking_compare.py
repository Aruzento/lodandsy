"""ARU-55: isolated structural checks, or --show for Windows acceptance.

Run from repository root: python -m prototypes.docking_compare --backend native
ADS is now a pinned app dependency. 'current' measures the migrated production host;
the historical custom-host 0x0 result is recorded in ADR-002.
These checks do not simulate mouse docking or prove mixed-DPI behavior.
"""

import argparse
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QPlainTextEdit


def native(app):
    window = QMainWindow()
    window.setDockNestingEnabled(True)
    docks = []
    for name in ["Card A", "Card B", "Map", "Tools"]:
        dock = QDockWidget(name, window)
        dock.setObjectName(name)
        dock.setWidget(QPlainTextEdit(name))
        window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        docks.append(dock)
    window.resize(1280, 800)
    window.splitDockWidget(docks[0], docks[2], Qt.Orientation.Horizontal)
    window.splitDockWidget(docks[2], docks[3], Qt.Orientation.Vertical)
    window.tabifyDockWidget(docks[0], docks[1])
    window.show()
    app.processEvents()
    assert docks[1] in window.tabifiedDockWidgets(docks[0])
    assert all(dock.width() > 0 and dock.height() > 0 for dock in docks)
    docks[3].setFloating(True)
    app.processEvents()
    floating = docks[3].isWindow() and docks[3].isFloating()
    native_title = docks[3].titleBarWidget() is None
    docks[3].showMaximized()
    app.processEvents()
    maximized = docks[3].isMaximized()
    docks[3].showNormal()
    docks[3].setFloating(False)
    saved = window.saveState(1)
    restored = window.restoreState(saved, 1)
    docks[3].close()
    docks[3].show()
    app.processEvents()
    return window, {
        "tab": True, "nonzero_documents": True, "float": floating,
        "native_title": native_title, "maximize": maximized,
        "restore_state": restored, "reopen": docks[3].isVisible(),
        "central_widget": window.centralWidget() is not None,
    }


def ads_backend(app):
    import PySide6QtAds as ads

    window = QMainWindow()
    manager = ads.CDockManager(window)
    docks = []
    for name in ["Card A", "Card B", "Map", "Tools"]:
        dock = ads.CDockWidget(manager, name)
        dock.setObjectName(name)
        dock.setWidget(QPlainTextEdit(name))
        docks.append(dock)
    area = manager.addDockWidget(ads.CenterDockWidgetArea, docks[0])
    manager.addDockWidget(ads.CenterDockWidgetArea, docks[1], area)
    map_area = manager.addDockWidget(ads.RightDockWidgetArea, docks[2], area)
    manager.addDockWidget(ads.BottomDockWidgetArea, docks[3], map_area)
    window.resize(1280, 800)
    window.show()
    app.processEvents()
    assert docks[0].dockAreaWidget() is docks[1].dockAreaWidget()
    assert all(dock.width() > 0 and dock.height() > 0 for dock in docks)
    docks[3].setFloating()
    app.processEvents()
    floating = docks[3].floatingDockContainer()
    is_window = floating is not None and floating.isWindow()
    native_title = floating is not None and not bool(
        floating.windowFlags() & Qt.WindowType.FramelessWindowHint
    )
    floating.showMaximized()
    app.processEvents()
    maximized = floating.isMaximized()
    floating.showNormal()
    manager.addDockWidget(ads.BottomDockWidgetArea, docks[3], map_area)
    saved = manager.saveState(1)
    restored = manager.restoreState(saved, 1)
    docks[3].toggleView(False)
    docks[3].toggleView(True)
    app.processEvents()
    return window, {
        "tab": True, "nonzero_documents": True, "float": is_window,
        "native_title_flags": native_title, "maximize": maximized,
        "restore_state": restored, "reopen": docks[3].isVisible(),
        "dock_areas": manager.dockAreaCount(),
    }


def current(app):
    from lodandsy.application.app_controller import AppController
    from lodandsy.ui.app_shell import AppShell

    window = AppShell()
    controller = AppController(window)
    a, b = controller.create_card("A"), controller.create_card("B")
    controller.open_card_editor(a.id)
    controller.open_card_editor(b.id)
    window.show()
    app.processEvents()
    rect = window.workspace.geometry()
    window._prototype_controller = controller
    return window, {"central_drop_target": [rect.width(), rect.height()]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["current", "native", "ads"], required=True)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    app = QApplication([])
    window, result = {"current": current, "native": native, "ads": ads_backend}[args.backend](app)
    window.setWindowTitle(f"LODANDSY docking prototype: {args.backend}")
    print(json.dumps({"backend": args.backend, "platform": app.platformName(), **result}))
    if args.show:
        return app.exec()
    window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
