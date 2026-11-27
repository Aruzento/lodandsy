"""Capture the v0.01 follow-up UI from actual Qt widgets in a disposable world."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QImage, QPainter, QPen, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from build_support.windows_smoke import wait
from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.application.project_history import ProjectHistory
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.theme import apply_theme


def capture(app, widget, output, name):
    app.processEvents()
    assert widget.isVisible(), name
    assert widget.grab().save(str(output / (name + ".png"))), name


def run(app, output, root):
    window = AppShell()
    controller = AppController(window)
    settings = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
    project = ProjectController(controller, ProjectHistory(settings))
    available = window.screen().availableGeometry()
    window.resize(min(1360, available.width()), min(860, available.height()))
    window.move(available.topLeft())
    window.show()
    try:
        assert project.create_project(root / "Этар")
        locations = controller.create_card("Северный берег", card_type="folder")
        archive = controller.create_card("Архив", card_type="folder")
        controller.create_card("Маяк", locations.id, card_type="location")
        controller.create_card("Маяк", archive.id, card_type="article")
        note = controller.create_card("Путевой журнал")
        controller.create_folder(locations.id)
        tree = window.tree_panel
        capture(app, tree, output, "01-folder")
        inline = next(
            edit for edit in tree.tree_view.viewport().findChildren(QLineEdit) if edit.isVisible()
        )
        QTest.keyClick(inline, Qt.Key.Key_Escape)

        note_window = controller.open_card_editor(note.id)
        editor = note_window.widget()
        edit = editor.text_edit
        edit.setPlainText("Береговые ориентиры")
        editor.format_toolbar.heading(2)
        edit.moveCursor(QTextCursor.MoveOperation.End)
        QTest.keyClick(edit, Qt.Key.Key_Return)
        QTest.keyClicks(edit, "[[")
        picker = editor.wiki_picker
        picker.query.setText("Маяк")
        capture(app, picker, output, "02-wiki-picker")
        QTest.keyClick(picker.query, Qt.Key.Key_Return)
        assert "lodandsy://entity/" in edit.toHtml()
        controller.window_manager.focus_window(note_window.key, floating=True)
        capture(app, editor.format_toolbar, output, "03-text-toolbar")
        capture(app, note_window.dock.floatingDockContainer(), output, "04-floating-note")
        note_window.close()

        card = controller.create_card("Дозорный маяка", card_type="character")
        sheet = controller.card_views.open_game_sheet(card.id).widget().game_sheet
        sheet.tiles["strength"].disclosure.setChecked(False)
        sheet.tiles["constitution"].disclosure.setChecked(False)
        app.processEvents()
        sheet.scroll.ensureWidgetVisible(sheet.tiles["strength"], 0, 8)
        capture(app, sheet, output, "05-ability-blocks")

        image = QImage(760, 500, QImage.Format.Format_RGB32)
        image.fill(0xFF425761)
        painter = QPainter(image)
        painter.setPen(QPen(Qt.GlobalColor.darkGray, 2))
        for y in range(30, 500, 80):
            painter.drawLine(0, y, 760, y)
        for x in range(30, 760, 80):
            painter.drawLine(x, 0, x, 500)
        painter.end()
        source = root / "Карта.png"
        assert image.save(str(source))
        controller.maps.import_map(source, "Северный берег")
        wait(app, lambda: not controller.maps.importing)
        document = next(iter(controller.maps_service.maps.values()))
        viewer = controller.maps.open_map(document.id).widget()
        wait(app, viewer.token_add.isEnabled)
        assert window.isAncestorOf(viewer)
        wait(app, lambda: bool(controller.maps.tiles.images))
        viewer.tool_state.activate("fog_hide")
        viewer.fog_tools.size.setValue(144)
        QTest.mouseMove(viewer.view.viewport(), viewer.view.viewport().rect().center())
        capture(app, window, output, "06-map-inspector")
        token = controller.actions.place_card(document.id, card.id, 160, 120)
        viewer.tool_state.activate("select")
        viewer.view.select_token(token.id)
        capture(app, window.inspector_panel, output, "07-token-inspector")
    finally:
        controller.shutdown_features()
        project.saver.shutdown()
        if project.store:
            project.store.close()
        window.close_guard = None
        window.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    apply_theme(app)
    with TemporaryDirectory(prefix="lodandsy-followup-") as directory:
        run(app, args.output, Path(directory))


if __name__ == "__main__":
    main()
