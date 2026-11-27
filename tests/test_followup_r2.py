import math

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from tests.test_map_tokens_grid import open_map

pytest_plugins = ["tests.project_fixture"]


def send_brush(view, kind, x, y):
    where = view.viewportTransform().map(QPointF(x, y))
    left, no_button = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    QApplication.sendEvent(view.viewport(), QMouseEvent(
        kind, where, QPointF(view.viewport().mapToGlobal(where.toPoint())),
        no_button if kind == QEvent.Type.MouseMove else left,
        no_button if kind == QEvent.Type.MouseButtonRelease else left,
        Qt.KeyboardModifier.NoModifier,
    ))


@pytest.mark.parametrize("erase", [False, True])
def test_long_brush_on_viewer_keeps_one_undo(project, tmp_path, qtbot, erase):
    app, projects = project
    document, viewer = open_map(app, projects, tmp_path, qtbot)
    view = viewer.view
    stack = app.maps_service.undo_stack(document.id)
    r = view.viewport().rect()
    assert not r.isEmpty()
    if erase:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainterPath

        path = QPainterPath()
        path.addRect(QRectF(0, 0, 500, 400))
        app.maps_service.edit_fog(document.id, path)
    index = stack.index()
    original = app.maps_service.get_map(document.id).fog
    tools = viewer.fog_tools
    tools.set_mode("erase" if erase else "hide")
    tools.size.setValue(12)
    send_brush(view, QEvent.Type.MouseButtonPress, 200, 180)
    for tick in range(720):
        send_brush(view, QEvent.Type.MouseMove,
                   200 + 110 * math.sin(0.08 * tick), 180 + 70 * math.sin(0.136 * tick))
    assert len(tools.points) > 512
    assert app.maps_service.get_map(document.id).fog == original and stack.index() == index
    send_brush(view, QEvent.Type.MouseButtonRelease, 200, 180)
    saved = app.maps_service.get_map(document.id).fog
    assert saved != original and stack.index() == index + 1
    stack.undo()
    assert app.maps_service.get_map(document.id).fog == original
    stack.redo()
    assert projects.save_current() and projects.store.load().maps[0].fog == saved


def test_sheet_real_rectangles_and_compact_default(project, qtbot):
    app, _projects = project
    card = app.create_card("Участник", card_type="character")
    actor = app.cards_service.create_actor(card.id)
    sheet = app.card_views.open_game_sheet(card.id, actor.actor_id).widget().game_sheet
    app.window.show()
    assert all(not tile.disclosure.isChecked() for tile in sheet.tiles.values())
    tile = sheet.tiles["wisdom"]
    tile.disclosure.setChecked(True)
    tile.base.setText("Длинная строка об источниках значения характеристики и модификатора " * 2)
    tile.base.show()
    for width in (1000, 770, 455):
        app.window.resize(width + 505, 950)
        QApplication.processEvents()
        assert tile.edit.isReadOnly()
        for block in sheet.tiles.values():
            assert block.rect().contains(block.edit.geometry())
            assert block.rect().contains(block.result.geometry())
        rows = [row.geometry() for row in tile.rows.values()]
        assert all(a.bottom() < b.top() for a, b in zip(rows, rows[1:]))
        assert all(tile.disclosure.body.rect().contains(rect) for rect in rows)
        assert tile.base.geometry().bottom() < rows[0].top()
        assert tile.rect().contains(tile.disclosure.body.geometry())


def test_hidden_and_dead_are_independent_and_never_leak_to_player(project, tmp_path, qtbot):
    from PySide6.QtGui import QColor, QImage

    from lodandsy.domain.actor_state import ActorRef
    from lodandsy.domain.card import Portrait

    app, projects = project
    document, viewer = open_map(app, projects, tmp_path, qtbot)
    card = app.create_card("Страж", card_type="character")
    portrait = QImage(32, 32, QImage.Format.Format_ARGB32)
    portrait.fill(QColor("#418598"))

    def attach(asset, error):
        assert not error
        app.cards_service.update_card(card.id, portrait=Portrait(asset.id))
        return True

    app.media.import_image(portrait, attach)
    qtbot.waitUntil(lambda: not app.media.importing)
    first = app.actions.place_card(document.id, card.id, 145, 138)
    other = app.actions.place_card(document.id, card.id, 340, 230)
    ref = ActorRef(card.id, first.actor_id)
    before = app.cards_service.get_actor(ref)
    view = viewer.view
    source = QImage(2, 1, QImage.Format.Format_ARGB32)
    source.setPixelColor(0, 0, QColor(18, 135, 255, 117))
    source.setPixelColor(1, 0, QColor(255, 80, 40, 0))
    muted = view._tokens[0]._grayscale(source)
    color = muted.pixelColor(0, 0)
    assert color.red() == color.green() == color.blue() and color.alpha() == 117
    assert muted.pixelColor(1, 0).alpha() == 0
    view.select_token(first.id)
    player = app.maps.open_presentation(document.id)
    qtbot.waitUntil(lambda: player.view._display_ready)

    def action(name):
        view.token_action.emit(first.id, name)
        return app.maps_service.get_map(document.id).tokens[0]

    action("portrait")
    assert len(app.maps._portrait_views) == 2
    assert action("kill").dead
    assert player.view._tokens[0].token.dead
    hidden = action("hide")
    assert hidden.hidden and hidden.dead
    assert not app.maps._portrait_views
    assert view.selected_token_id() == first.id and view._tokens[0].isVisible()
    assert app.window.inspector_panel.pages.currentWidget() is viewer.tools.hidden_token
    assert [item.token for item in player.view._tokens] == [other]
    view.measurement_changed.emit((first.id, (145, 138), (204, 142)))
    view.transient_changed.emit("token", first.id, 204, 142)
    assert player.view.measurement is None and len(player.view._tokens) == 1
    action("portrait")
    assert not app.maps._portrait_views
    stack = app.maps_service.undo_stack(document.id)
    stack.undo()
    assert player.view._tokens[0].token.dead and not player.view._tokens[0].token.hidden
    stack.redo()
    assert [item.token for item in player.view._tokens] == [other]
    viewer.tools.show_token_requested.emit()
    assert player.view._tokens[0].token.dead and app.cards_service.get_actor(ref) == before
    assert not action("revive").dead
    assert action("hide").hidden
    assert action("kill").dead
    assert projects.save_current()
    assert projects.store.load().maps[0].tokens[0].dead
    assert projects.store.load().maps[0].tokens[0].hidden


def test_token_picker_filters_and_waits_for_actor_confirmation(
    project, tmp_path, qtbot, monkeypatch,
):
    from PySide6.QtWidgets import QInputDialog

    from lodandsy.ui.entity_picker import EntityPicker

    app, projects = project
    document, viewer = open_map(app, projects, tmp_path, qtbot)
    parent = app.create_card("Застава", card_type="folder")
    card = app.create_card("Дозорный", parent.id, card_type="character")
    app.create_card("Дозорный", card_type="creature")
    app.tables_service.create_table("Дозорный")
    previous = app.cards_service.create_actor(card.id)

    def pick(picker):
        assert picker.types.currentText() == "Все типы"
        picker.query.setText("Дозорный")
        assert len(picker.model.ids) == 2
        picker.types.setCurrentIndex(picker.types.findData("character"))
        assert picker.model.ids == (card.id,)
        row = picker.model.index(0)
        assert "Застава" in row.data() and not row.data(Qt.ItemDataRole.DecorationRole).isNull()
        picker.chosen_id = card.id
        return 1

    monkeypatch.setattr(EntityPicker, "exec", pick)
    monkeypatch.setattr(QInputDialog, "getItem", lambda *args: ("", False))
    app.maps._add_token(document.id, 180, 170)
    assert not app.maps_service.get_map(document.id).tokens
    assert len(app.cards.get(card.id).actors) == 1
    monkeypatch.setattr(QInputDialog, "getItem", lambda *args: (args[3][1], True))
    app.maps._add_token(document.id, 180, 170)
    token, = app.maps_service.get_map(document.id).tokens
    assert token.actor_id == previous.actor_id and viewer.view.selected_token_id() == token.id
    assert len(app.cards.get(card.id).actors) == 1 and projects.save_current()


def test_rich_toolbar_wraps_and_edits_office_browser_html(project, tmp_path, qtbot):
    from PySide6.QtCore import QMimeData, QUrl
    from PySide6.QtGui import QTextCursor, QTextFormat
    from PySide6.QtWidgets import QToolButton

    from lodandsy.ui.rich_toolbar import selected_runs

    app, projects = project
    assert projects.create_project(tmp_path / "world")
    card = app.create_card("Проверка форматирования")
    window = app.open_card_editor(card.id)
    editor = window.widget()
    app.window_manager.focus_window(window.key, floating=True)
    floating = window.dock.floatingDockContainer()
    toolbar, edit = editor.format_toolbar, editor.text_edit
    for width in (980, 520, 340):
        floating.resize(width, 840)
        QApplication.processEvents()
        for button in toolbar.findChildren(QToolButton):
            assert button.isVisible() and not button.icon().isNull()
            where = button.mapTo(toolbar, button.rect().topLeft())
            assert toolbar.rect().contains(where + button.rect().bottomRight())
    assert toolbar.rows.count() > 1
    assert "Формат" not in {button.text() for button in toolbar.findChildren(QToolButton)}
    toolbar.sync_paragraph()
    assert toolbar.color.currentData() != "#000000"

    payload = QMimeData()
    payload.setUrls([QUrl("https://example.com/")])
    payload.setHtml(
        '<html><body style="font-family:Georgia;color:rgb(10, 50, 90)">'
        '<p style="text-align:right"><span style="font-size:21px;mso-bidi-font-size:12pt;'
        'background-color:rgb(90, 140, 190)">Office\n sample</span><b> browser</b></p>'
        '<p><a href="javascript:void(0)">Unsafe</a><a href="https://example.com/">Safe</a>'
        '<img src="https://example.com/resource.png"><script>DoNotRun</script></p>'
        '<pre>code\n  indented</pre></body></html>'
    )
    edit.insertFromMimeData(payload)
    assert "Office sample browser" in edit.toPlainText() and "DoNotRun" not in edit.toPlainText()
    assert "code\n  indented" in edit.toPlainText()
    assert "javascript:" not in edit.toHtml() and "resource.png" not in edit.toHtml()
    cursor = edit.textCursor()
    cursor.setPosition(2)
    edit.setTextCursor(cursor)
    assert toolbar.color.currentData() == "#0a325a"
    assert toolbar.highlight.currentData() == "#5a8cbe"
    cursor.setPosition(0)
    cursor.setPosition(len("Office sample browser"), QTextCursor.MoveMode.KeepAnchor)
    edit.setTextCursor(cursor)
    source = selected_runs(cursor)
    assert source[0][2].fontFamilies() == ["Georgia"]
    assert source[0][2].foreground().color().name() == "#0a325a"
    assert source[0][2].background().color().name() == "#5a8cbe"
    toolbar.character(fontPointSize=18)
    assert all(style.fontPointSize() == 18 and not style.hasProperty(
        QTextFormat.Property.FontPixelSize
    ) for _, _, style in selected_runs(edit.textCursor()))
    toolbar.heading(2)
    assert edit.document().firstBlock().blockFormat().headingLevel() == 2
    toolbar.apply("clear")
    assert edit.document().firstBlock().blockFormat().headingLevel() == 0
    assert all(not style.hasProperty(QTextFormat.Property.BackgroundBrush)
               for _, _, style in selected_runs(edit.textCursor()))
    edit.undo()
    assert edit.document().firstBlock().blockFormat().headingLevel() == 2
    assert projects.save_current()
    app.window_manager.close_window(window.key)
    restored = app.open_card_editor(card.id).widget().text_edit
    assert restored.document().firstBlock().blockFormat().headingLevel() == 2
    assert "https://example.com/" in restored.toHtml()
