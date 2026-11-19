import base64
import json
import os
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QApplication

UI_STATE_NAME = ".lodandsy-ui.json"


def capture_workspace(controller):
    panel = controller.window.tree_panel
    current_ids = {card.id for card in controller.cards.all()}
    states = {
        key: values
        for key, values in controller.saved_card_preferences.items()
        if key in current_ids
    }
    for card_id, editor in controller.card_editors.items():
        state = controller.card_document_states[card_id]
        state.capture(editor)
    for card_id, state in controller.card_document_states.items():
        states[card_id] = state.ui_values()
    cameras = {
        key: camera
        for key, camera in controller.modules._map_ui.items()
        if key in controller.modules.session.maps
    }
    for key in controller.window_manager.window_keys():
        if key.startswith("map:"):
            camera = controller.window_manager.find_window(key).widget().camera_state()
            if camera is not None:
                cameras[key[4:]] = camera
    tables = {key: value for key,value in controller.modules._table_ui.items()
              if key in controller.modules.session.tables}
    for key in controller.window_manager.window_keys():
        if key.startswith("table:"):
            tables[key[6:]] = controller.window_manager.find_window(key).widget().ui_state()
    return {
        "version": 3,
        "documents": list(controller.window_manager.window_keys()),
        "active": controller.window_manager.active_window_key,
        "entity_selected": controller.session.current_entity_id,
        "navigator_selected": controller.window.tree_panel.current_node_key(),
        "navigator_expanded": panel.expanded_keys(),
        "navigator_scroll": panel.tree_view.verticalScrollBar().value(),
        "cards": states,
        "maps": cameras,
        "tables": tables,
        "dice_selected": {key: value.get("selected")
                          for key,value in controller.modules._dice_runtime.items()
                          if key in controller.modules.session.dice},
        "geometry": base64.b64encode(bytes(controller.window.saveGeometry())).decode("ascii"),
        "chrome": base64.b64encode(bytes(controller.window.saveState(1))).decode("ascii"),
        "layout": base64.b64encode(bytes(controller.window.workspace.saveState(1))).decode("ascii"),
    }


def restore_workspace(controller, data):
    if not isinstance(data, dict) or data.get("version") != 3:
        raise ValueError("Неподдерживаемая версия раскладки")
    documents = data.get("documents")
    if not isinstance(documents, list) or not all(isinstance(key, str) for key in documents):
        raise ValueError("Повреждён список документов раскладки")
    geometry = base64.b64decode(data.get("geometry", ""), validate=True)
    layout = base64.b64decode(data.get("layout", ""), validate=True)
    chrome = base64.b64decode(data.get("chrome", ""), validate=True)
    complete = True
    for key in documents:
        try:
            controller.open_document(key)
        except ValueError:
            complete = False
    if geometry:
        controller.window.restoreGeometry(QByteArray(geometry))
    if chrome:
        controller.window.restoreState(QByteArray(chrome), 1)
    if complete and layout:
        if not controller.window.workspace.restoreState(QByteArray(layout), 1):
            raise ValueError("Не удалось восстановить раскладку; открыты стандартные вкладки")
    QApplication.processEvents()
    controller.window.workspace.ensure_visible()
    cameras = data.get("maps", {})
    if isinstance(cameras, dict):
        controller.modules._map_ui.update(
            {
                key: camera
                for key, camera in cameras.items()
                if key in controller.modules.session.maps and isinstance(camera, dict)
            }
        )
        for key, camera in cameras.items():
            window = controller.window_manager.find_window(f"map:{key}")
            if window and isinstance(camera, dict):
                window.widget().restore_camera_state(camera)
    tables = data.get("tables", {})
    if isinstance(tables, dict):
        controller.modules._table_ui.update(
            {
                key: value
                for key, value in tables.items()
                if key in controller.modules.session.tables and isinstance(value, dict)
            }
        )
        for key, value in tables.items():
            window = controller.window_manager.find_window(f"table:{key}")
            if window:
                window.widget().restore_ui(value)
    selected_dice = data.get("dice_selected", {})
    if isinstance(selected_dice, dict):
        for key,selected in selected_dice.items():
            window = controller.window_manager.find_window(f"dice:{key}")
            if window and isinstance(selected,str):
                window.widget().select_preset(selected)
    saved = data.get("cards", {})
    if not isinstance(saved, dict):
        raise ValueError("Повреждён список настроек карточек")
    ids = {card.id for card in controller.cards.all()}
    controller.saved_card_preferences = {
        key: values for key, values in saved.items() if key in ids and isinstance(values, dict)
    }
    for card_id, editor in controller.card_editors.items():
        values = controller.saved_card_preferences.get(card_id)
        if values is not None:
            state = controller.card_document_states[card_id]
            state.load_ui_values(values)
            state.restore(editor)
    panel = controller.window.tree_panel
    navigator_expanded = data.get("navigator_expanded")
    if isinstance(navigator_expanded, list):
        panel.tree_view.collapseAll()
        for key in navigator_expanded:
            if isinstance(key, str):
                panel.tree_view.setExpanded(panel.tree_model.index_for_node(key), True)
    selected = data.get("entity_selected")
    if isinstance(selected, str):
        try:
            controller.session.select_entity(selected)
        except ValueError:
            controller.session.clear_selection()
    else:
        controller.session.clear_selection()
    navigator_selected = data.get("navigator_selected")
    if isinstance(navigator_selected, str):
        index = panel.tree_model.index_for_node(navigator_selected)
        if index.isValid():
            panel.tree_view.setCurrentIndex(index)
    navigator_scroll = data.get("navigator_scroll")
    if type(navigator_scroll) is int and navigator_scroll >= 0:
        bar = panel.tree_view.verticalScrollBar()
        bar.setValue(min(navigator_scroll, bar.maximum()))
    active = data.get("active")
    if isinstance(active, str):
        controller.window_manager.focus_window(active)


def load_workspace_file(root: Path):
    path = root / UI_STATE_NAME
    if not path.exists():
        return None
    if path.stat().st_size > 5_000_000:
        raise ValueError("Файл раскладки превышает допустимый размер")
    return json.loads(path.read_text(encoding="utf-8"))


def save_workspace_file(root: Path, data):
    path = root / UI_STATE_NAME
    temporary = root / f"{UI_STATE_NAME}.{uuid4().hex}.tmp"
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
