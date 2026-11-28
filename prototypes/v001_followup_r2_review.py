"""Capture R2 on the Windows Qt platform using synthetic project data."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QPointF, QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from build_support.windows_smoke import wait
from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.application.project_history import ProjectHistory
from lodandsy.domain.card import Portrait
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.entity_picker import EntityPicker
from lodandsy.ui.theme import apply_theme


def capture(app, widget, output, name):
    app.processEvents()
    assert widget.isVisible() and widget.grab().save(str(output / (name + ".png"))), name


def assets(app, controller, root, card):
    portrait = QImage(120, 120, QImage.Format.Format_ARGB32)
    portrait.fill(Qt.GlobalColor.transparent)
    painter = QPainter(portrait)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#8aa8bd"))
    painter.setPen(QPen(QColor("#314e5d"), 3))
    painter.drawEllipse(4, 4, 112, 112)
    painter.setBrush(QColor("#ad7851"))
    painter.drawEllipse(31, 14, 58, 57)
    painter.setBrush(QColor("#44766e"))
    painter.drawEllipse(21, 69, 78, 39)
    painter.end()

    def attach(asset, error):
        assert not error, error
        controller.cards_service.update_card(card.id, portrait=Portrait(asset.id))
        return True

    controller.media.import_image(portrait, attach)
    wait(app, lambda: not controller.media.importing)
    background = QImage(760, 490, QImage.Format.Format_RGB32)
    background.fill(QColor("#47575c"))
    painter = QPainter(background)
    painter.setPen(QPen(QColor("#6a7e83"), 2))
    for y in range(5, 490, 64):
        painter.drawLine(0, y, 760, y)
    for x in range(5, 760, 64):
        painter.drawLine(x, 0, x, 490)
    painter.end()
    source = root / "Северный берег.png"
    assert background.save(str(source))
    return source


def picker_capture(app, viewer, output):
    finished = []

    def save_picker():
        picker = next(w for w in QApplication.topLevelWidgets()
                      if isinstance(w, EntityPicker) and w.isVisible())
        try:
            picker.query.setText("Дозорный")
            capture(app, picker, output, "04-token-picker")
            finished.append(True)
        finally:
            picker.reject()

    QTimer.singleShot(120, save_picker)
    viewer.tools.actions["token"].trigger()
    QTest.mouseClick(viewer.view.viewport(), Qt.MouseButton.LeftButton,
                     pos=viewer.view.mapFromScene(QPointF(155, 155)))
    assert finished


def run(app, output, root):
    window = AppShell()
    controller = AppController(window)
    settings = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
    projects = ProjectController(controller, ProjectHistory(settings))
    available = window.screen().availableGeometry()
    window.resize(min(1440, available.width()), min(900, available.height()))
    window.move(available.topLeft())
    window.show()
    try:
        assert projects.create_project(root / "Север")
        north = controller.create_card("Северная застава", card_type="folder")
        south = controller.create_card("Южная застава", card_type="folder")
        card = controller.create_card("Дозорный", north.id, card_type="character")
        controller.create_card("Дозорный", south.id, card_type="character")
        note = controller.create_card("Журнал")
        note_window = controller.open_card_editor(note.id)
        editor = note_window.widget()
        editor.text_edit.setPlainText("Северный тракт\nПроверить проход к маяку.\nЛагерь у воды.")
        editor.text_edit.moveCursor(QTextCursor.MoveOperation.Start)
        editor.format_toolbar.heading(1)
        capture(app, editor, output, "01-text-editor")
        controller.window_manager.focus_window(note_window.key, floating=True)
        floating = note_window.dock.floatingDockContainer()
        floating.resize(385, min(640, available.height()))
        capture(app, floating, output, "02-narrow-text-editor")
        note_window.close()

        sheet = controller.card_views.open_game_sheet(card.id).widget().game_sheet
        sheet.tiles["dexterity"].disclosure.setChecked(True)
        sheet.tiles["wisdom"].disclosure.setChecked(True)
        app.processEvents()
        sheet.scroll.ensureWidgetVisible(sheet.tiles["dexterity"], 0, 10)
        capture(app, sheet, output, "03-abilities")

        controller.maps.import_map(assets(app, controller, root, card), "Северный берег")
        wait(app, lambda: not controller.maps.importing)
        document = next(iter(controller.maps_service.maps.values()))
        viewer = controller.maps.open_map(document.id).widget()
        wait(app, viewer.token_add.isEnabled)
        wait(app, lambda: bool(controller.maps.tiles.images))
        picker_capture(app, viewer, output)
        view = viewer.view
        first = controller.actions.place_card(document.id, card.id, 175, 205)
        second = controller.actions.place_card(document.id, card.id, 300, 205)
        controller.actions.place_card(document.id, card.id, 425, 205)
        view.token_action.emit(first.id, "hide")
        view.token_action.emit(second.id, "kill")
        documents = iter((("note", "Дневник"), ("inventory", "Припасы")))
        controller.maps.request_note_document = lambda: next(documents)
        for x in (265, 390):
            viewer.tools.actions["note"].trigger()
            QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                             pos=view.mapFromScene(QPointF(x, 315)))
        assert len(controller.maps_service.get_map(document.id).notes) == 2
        viewer.vector_tools.select(None)
        view.select_token(first.id)
        wait(app, lambda: controller.media.cached_preview(
            projects.store.root, view._tokens[0].asset_path
        ) is not None)
        capture(app, window, output, "05-gm-map-status-and-notes")
        player = controller.maps.open_presentation(document.id)
        wait(app, lambda: player.view._display_ready)
        assert not player.view.vector_notes and len(player.view._tokens) == 2
        capture(app, player.view, output, "06-player-map")
    finally:
        controller.shutdown_features()
        projects.saver.shutdown()
        if projects.store:
            projects.store.close()
        window.close_guard = None
        window.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    apply_theme(app)
    with TemporaryDirectory(prefix="lodandsy-followup-r2-") as directory:
        run(app, args.output, Path(directory))


if __name__ == "__main__":
    main()
