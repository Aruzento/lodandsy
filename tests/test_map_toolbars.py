from PySide6.QtCore import QEvent, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QComboBox, QInputDialog, QToolButton

from lodandsy.domain.map_document import MapPortal, MapShape
from tests.test_map_tokens_grid import open_map

pytest_plugins = ["tests.project_fixture"]


def ready(project, tmp_path, qtbot):
    app, session = project
    document, widget = open_map(app, session, tmp_path, qtbot)
    assert app.window.isVisible() and widget.view.isVisible()
    qtbot.waitUntil(lambda: app.window.windowHandle().isExposed())
    return app, session, document, widget


def test_single_state_projections_and_no_shape_combo(project, tmp_path, qtbot):
    app, session, document, widget = ready(project, tmp_path, qtbot)
    card = app.create_card("Герой", card_type="character")
    app.maps_service.add_token(document.id, card.id, 100, 100)
    item = widget.view._tokens[0]
    item.setSelected(True)
    for tool in (
        "pan",
        "token",
        "cone",
        "vertices",
        "portal",
        "fog_hide",
        "fog_erase",
        "fog_polygon",
        "fog_select",
        "select",
    ):
        widget.tool_state.activate(tool)
        assert item.isSelected(), "Switching tools must preserve the Inspector selection"
        assert widget.view.tool == tool
        assert (
            "mode" not in widget.fog_tools.__dict__ and "mode" not in widget.vector_tools.__dict__
        )
        checked = [key for key, a in widget.tools.actions.items() if a.isChecked()]
        assert checked == ["shape" if tool == "cone" else "select" if tool == "vertices" else tool]
        assert widget.fog_tools.isVisible() == tool.startswith("fog_")
    assert not hasattr(widget.vector_tools, "choice")
    assert not widget.vector_tools.findChildren(QComboBox)
    for action in widget.tools.actions.values():
        button = widget.tools.sidebar.widgetForAction(action)
        assert isinstance(button, QToolButton) and button.iconSize().width() == 18
    app.maps.tiles.failed.emit("Ошибка чтения тайла")
    assert widget.message.isVisible() and widget.message.text() == "Ошибка чтения тайла"


def test_shape_returns_to_select_and_remembers_last(project, tmp_path, qtbot):
    app, session, document, widget = ready(project, tmp_path, qtbot)
    widget.tools.shape_actions["triangle"].trigger()
    tools = widget.vector_tools
    tools.points = [(100, 100), (200, 100), (150, 200)]
    tools.finish()
    assert len(app.maps_service.get_map(document.id).shapes) == 1
    assert widget.tool_state.active == "select" and widget.tool_state.last_shape == "triangle"
    widget.tools.actions["shape"].trigger()
    assert widget.tool_state.active == "triangle"
    before = session.saver.revision
    tools.points = [(100, 100), (100, 100), (150, 200)]
    tools.finish()
    assert session.saver.revision == before and widget.tool_state.active == "triangle"


def test_keyboard_space_switch_cancel_and_text_focus(project, tmp_path, qtbot):
    app, session, document, widget = ready(project, tmp_path, qtbot)
    view = widget.view
    view.setFocus()
    for key, mode in (
        (Qt.Key.Key_B, "fog_hide"),
        (Qt.Key.Key_E, "fog_erase"),
        (Qt.Key.Key_H, "pan"),
        (Qt.Key.Key_V, "select"),
        (Qt.Key.Key_M, "circle"),
    ):
        qtbot.keyClick(view, key)
        assert widget.tool_state.active == mode
    tools = widget.vector_tools
    tools.points = [(100, 100), (200, 100)]
    before = session.saver.revision
    qtbot.keyPress(view, Qt.Key.Key_Space)
    assert widget.tool_state.active == "pan" and not tools.points
    qtbot.keyRelease(view, Qt.Key.Key_Space)
    assert widget.tool_state.active == "circle"
    tools.points = [(100, 100), (200, 100)]
    qtbot.keyClick(view, Qt.Key.Key_Escape)
    assert not tools.points and session.saver.revision == before
    value = MapShape("circle", ((40, 0),), x=100, y=100)
    app.maps_service.put_vector(document.id, value)
    widget.tool_state.activate("select")
    tools.select(value)
    tools.name.setFocus()
    tools.name.clear()
    qtbot.keyClicks(tools.name, "vhbem ")
    assert widget.tool_state.active == "select" and tools.name.text() == "vhbem "
    widget.tool_state.activate("fog_hide")
    qtbot.keyClick(widget.fog_tools.size.lineEdit(), Qt.Key.Key_H)
    assert widget.tool_state.active == "fog_hide"


def test_two_maps_tool_independence_and_ordinary_portal_double_click(project, tmp_path, qtbot):
    app, session, document, widget = ready(project, tmp_path, qtbot)
    target = app.maps_service.create_map("Other", document.asset_id)
    other = app.maps.open_map(target.id).widget()
    widget.tool_state.activate("cone")
    other.tool_state.activate("fog_erase")
    assert widget.tool_state.active == "cone" and other.tool_state.active == "fog_erase"
    portal = MapPortal(target.id, 200, 150)
    app.maps_service.put_vector(document.id, portal)
    widget.tool_state.activate("select")
    hits = []
    widget.vector_tools.portal_opened.connect(hits.append)
    qtbot.mouseDClick(
        widget.view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=widget.view.mapFromScene(QPointF(200, 150)),
    )
    assert hits == [portal.id]
    assert widget.tool_state.active == "select" and other.tool_state.active == "fog_erase"


def test_grid_toggle_uses_same_undo(project, tmp_path, qtbot):
    app, session, document, widget = ready(project, tmp_path, qtbot)
    old = app.maps_service.get_map(document.id).grid.enabled
    widget.tools.grid.trigger()
    assert app.maps_service.get_map(document.id).grid.enabled is not old
    app.maps_service.undo_stack(document.id).undo()
    assert app.maps_service.get_map(document.id).grid.enabled == old
    assert widget.tools.grid.isChecked() == old


def test_portal_cancel_and_success_return_only_after_commit(project, tmp_path, qtbot, monkeypatch):
    from lodandsy.application import maps_controller

    app, session, document, widget = ready(project, tmp_path, qtbot)
    target = app.maps_service.create_map("Цель", document.asset_id)
    accepted = False

    class Picker:
        chosen_id = target.id

        def __init__(self, *args, **kwargs):
            pass

        def setWindowTitle(self, title):
            pass

        def exec(self):
            return accepted

        def deleteLater(self):
            pass

    monkeypatch.setattr(maps_controller, "EntityPicker", Picker)
    monkeypatch.setattr(maps_controller.MapPortalDialog, "exec", lambda self: True)
    widget.tools.actions["portal"].trigger()
    before = session.saver.revision
    widget.vector_tools.portal_requested.emit(100, 100)
    assert widget.tool_state.active == "portal" and session.saver.revision == before
    accepted = True
    widget.vector_tools.portal_requested.emit(100, 100)
    assert widget.tool_state.active == "select"
    assert app.maps_service.get_map(document.id).portals[0].target_id == target.id
    app.maps_service.undo_stack(document.id).undo()
    assert not app.maps_service.get_map(document.id).portals


def test_brush_eraser_sticky_switch_cancels_and_space_pans(project, tmp_path, qtbot):
    app, session, document, widget = ready(project, tmp_path, qtbot)
    view = widget.view
    for mode in ("fog_hide", "fog_erase"):
        widget.tools.actions[mode].trigger()
        start = view.mapFromScene(QPointF(200, 200))
        qtbot.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        assert widget.tool_state.active == mode and not widget.fog_tools.points
    before = session.saver.revision
    widget.fog_tools.points = [(100, 100), (200, 200)]
    widget.fog_tools._preview()
    widget.tools.actions["shape"].trigger()
    assert not widget.fog_tools.points and view._fog_preview.isEmpty()
    view.scale(5, 5)
    view.centerOn(250, 200)
    old = view.mapToScene(view.viewport().rect().center())
    qtbot.keyPress(view, Qt.Key.Key_Space)
    start = view.viewport().rect().center()
    qtbot.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    destination = QPointF(start.x() + 40, start.y() + 30)
    QApplication.sendEvent(
        view.viewport(),
        QMouseEvent(
            QEvent.Type.MouseMove,
            destination,
            view.viewport().mapToGlobal(destination.toPoint()),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=destination.toPoint())
    qtbot.keyRelease(view, Qt.Key.Key_Space)
    assert widget.tool_state.active == "circle" and session.saver.revision == before
    assert view.mapToScene(view.viewport().rect().center()) != old


def test_token_tool_uses_clicked_world_position(project, tmp_path, qtbot, monkeypatch):
    app, session, document, widget = ready(project, tmp_path, qtbot)
    card = app.create_card("Участник")
    monkeypatch.setattr(QInputDialog, "getItem", lambda *args, **kwargs: (args[3][1], True))
    widget.tools.actions["token"].trigger()
    point = widget.view.mapFromScene(QPointF(150, 160))
    expected = widget.view.mapToScene(point)
    qtbot.mouseClick(widget.view.viewport(), Qt.MouseButton.LeftButton, pos=point)
    token = app.maps_service.get_map(document.id).tokens[0]
    assert token.card_id == card.id
    assert (token.x, token.y) == (expected.x(), expected.y())


def test_native_overflow_keeps_hidden_actions_accessible(project, tmp_path, qtbot):
    app, session, document, widget = ready(project, tmp_path, qtbot)
    dock = app.maps.open_map(document.id).dock
    dock.setFloating()
    floating = dock.floatingDockContainer()
    floating.show()
    floating.resize(320, 300)
    QApplication.processEvents()
    floating.resize(320, 300)
    qtbot.waitUntil(lambda: widget.tools.sidebar.height() < 500)
    extension = widget.tools.sidebar.findChild(QToolButton, "qt_toolbar_ext_button")
    assert extension is not None and extension.isVisible()
    assert widget.tools.sidebar.rect().contains(extension.geometry()), (
        extension.geometry(),
        widget.tools.sidebar.rect(),
    )
    assert widget.tools.sidebar.widgetForAction(widget.tools.actions["select"]).size().width() == 36
    menu = extension.menu()
    assert menu and widget.tools.actions["fog_select"] in menu.actions()
    widget.tools.actions["fog_select"].trigger()
    assert widget.tool_state.active == "fog_select"
    widget.tool_state.activate("fog_hide")
    QApplication.processEvents()
    assert widget.width() <= floating.width()
    for control in (widget.fog_tools.size, widget.fog_tools.opacity):
        bounds = QRect(control.mapTo(widget, control.rect().topLeft()), control.size())
        assert control.isVisible() and widget.rect().contains(bounds)
    widget.tool_state.activate("select")
    floating.resize(200, 300)
    QApplication.processEvents()
    extension = widget.tools.general.findChild(QToolButton, "qt_toolbar_ext_button")
    assert extension.isVisible() and widget.tools.general.rect().contains(extension.geometry())
    assert "Презентация игрокам" in [a.text() for a in extension.menu().actions()]


def test_compact_groups_editor_and_flyout_bounds(project, tmp_path, qtbot):
    from PySide6.QtCore import QPoint

    app, session, document, widget = ready(project, tmp_path, qtbot)
    tools = widget.tools
    assert "measure" not in tools.actions and "vertices" not in tools.actions
    tools.selection_actions["vertices"].trigger()
    assert widget.tool_state.active == "vertices" and tools.actions["select"].isChecked()
    tools.actions["pan"].trigger()
    tools.actions["select"].trigger()
    assert widget.tool_state.active == "vertices"
    qtbot.keyClick(widget.view, Qt.Key.Key_V)
    assert widget.tool_state.active == "select"
    buttons = tools.general.findChildren(QToolButton)
    labelled = [
        b for b in buttons if b.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    ]
    assert len(labelled) == 1 and labelled[0].text() == "Редактор карты"
    assert tools.general.actions()[-1] is labelled[0].defaultAction()
    assert tools.sidebar.iconSize().width() == 18
    assert any(
        a.objectName() == "fogSeparator" and a.isSeparator() for a in tools.sidebar.actions()
    )
    for key in ("select", "shape"):
        button = tools.sidebar.widgetForAction(tools.actions[key])
        menu = tools.actions[key].menu()
        menu.popup(button.mapToGlobal(QPoint(button.width(), 0)))
        QApplication.processEvents()
        bounds = button.screen().availableGeometry()
        assert bounds.contains(menu.geometry())
        assert menu.x() - button.mapToGlobal(QPoint(button.width(), 0)).x() == 10
        menu.close()
    # Place the same native menu beside a button at the right/bottom screen edge.
    from lodandsy.ui.map_tools import ToolMenu

    anchor = QToolButton()
    qtbot.addWidget(anchor)
    anchor.resize(36, 36)
    bounds = anchor.screen().availableGeometry()
    anchor.move(bounds.right() - 35, bounds.bottom() - 35)
    anchor.show()
    menu = ToolMenu(anchor)
    menu.addAction("Многоугольник")
    menu.popup(anchor.mapToGlobal(QPoint(36, 0)))
    QApplication.processEvents()
    assert bounds.contains(menu.geometry())
    assert menu.geometry().right() < anchor.x()
    menu.close()


def test_grid_dialog_owns_measurement_cancel_and_new_map_defaults(
    project, tmp_path, qtbot, monkeypatch
):
    from dataclasses import replace

    from PySide6.QtCore import QSettings

    from lodandsy.ui.map_settings_dialogs import MapGridDialog

    app, session, document, widget = ready(project, tmp_path, qtbot)
    assert app.maps_service.get_map(document.id).grid.feet_per_cell == 5
    unknown = replace(document.grid, feet_per_cell=None)
    app.maps_service.edit_map(document.id, grid=unknown)
    settings = QSettings(str(tmp_path / "measurement.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr("lodandsy.application.maps_controller.QSettings", lambda: settings)
    before = session.saver.revision
    previous_mode = widget.view.measurement_mode
    accepted = False

    def edit(dialog):
        assert not dialog.scale_known.isChecked()
        assert [dialog.measurement_mode_combo.itemText(i) for i in range(2)] == [
            "D&D 5e 2014",
            "Геометрическое",
        ]
        dialog.show()
        assert not dialog.grab().isNull()
        dialog.measurement_mode_combo.setCurrentIndex(
            dialog.measurement_mode_combo.findData("geometry")
        )
        return accepted

    monkeypatch.setattr(MapGridDialog, "exec", edit)
    app.maps._grid_settings(document.id)
    assert session.saver.revision == before and widget.view.measurement_mode == previous_mode
    accepted = True
    app.maps._grid_settings(document.id)
    assert widget.view.measurement_mode == "geometry"
    assert settings.value("maps/measurement") == "geometry"
    assert app.maps_service.get_map(document.id).grid == unknown
    assert session.saver.revision == before


def test_portal_dialog_hide_label_edit_cancel_undo_and_navigation(
    project, tmp_path, qtbot, monkeypatch
):
    from lodandsy.application import maps_controller

    app, session, document, widget = ready(project, tmp_path, qtbot)
    target = app.maps_service.create_map("Цель", document.asset_id)
    portal = MapPortal(target.id, 100, 100, "Сохраняемое имя")
    app.maps_service.put_vector(document.id, portal)

    class Picker:
        chosen_id = target.id

        def __init__(self, *a, **kw):
            pass

        def setWindowTitle(self, title):
            pass

        def exec(self):
            return True

        def deleteLater(self):
            pass

    accepted = False

    def edit(dialog):
        assert dialog.label.text() == portal.label
        assert dialog.hide_label.text() == "Не показывать название на карте"
        dialog.hide_label.setChecked(True)
        return accepted

    monkeypatch.setattr(maps_controller, "EntityPicker", Picker)
    monkeypatch.setattr(maps_controller.MapPortalDialog, "exec", edit)
    before = session.saver.revision
    app.maps._portal_edit(document.id, portal.id)
    assert session.saver.revision == before
    accepted = True
    app.maps._portal_edit(document.id, portal.id)
    saved = app.maps_service.get_map(document.id).portals[0]
    assert saved.hide_label and saved.label == portal.label and saved.id == portal.id
    stack = app.maps_service.undo_stack(document.id)
    stack.undo()
    assert app.maps_service.get_map(document.id).portals == (portal,)
    stack.redo()
    assert app.maps_service.get_map(document.id).portals == (saved,)
    hits = []
    widget.vector_tools.portal_opened.connect(hits.append)
    qtbot.mouseDClick(
        widget.view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=widget.view.mapFromScene(QPointF(100, 100)),
    )
    assert hits == [portal.id]
