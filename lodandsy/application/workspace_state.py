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
    states = {}
    for card_id, editor in controller.card_editors.items():
        state = controller.card_document_states[card_id]
        state.capture(editor)
        states[card_id] = {name: getattr(state, name) for name in [
            "position", "anchor", "vertical_scroll", "horizontal_scroll", "preview_scroll", "mode",
            "splitter_sizes",
        ]}
    return {
        "version": 1,
        "documents": list(controller.window_manager.window_keys()),
        "active": controller.window_manager.active_window_key,
        "selected": controller.session.current_card_id,
        "expanded": [key for key in panel.tree_model.card_ids()
                     if panel.tree_view.isExpanded(panel.tree_model.index_for_card(key))],
        "cards": states,
        "maps": {key[4:]: (controller.window_manager.find_window(key).widget().pending_camera
                          or controller.window_manager.find_window(key).widget().view.camera())
                 for key in controller.window_manager.window_keys() if key.startswith("map:")},
        "geometry": base64.b64encode(bytes(controller.window.saveGeometry())).decode("ascii"),
        "chrome": base64.b64encode(bytes(controller.window.saveState(1))).decode("ascii"),
        "layout": base64.b64encode(bytes(controller.window.workspace.saveState(1))).decode("ascii"),
    }


def restore_workspace(controller, data):
    if not isinstance(data, dict) or data.get("version") != 1:
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
        for key, camera in cameras.items():
            window = controller.window_manager.find_window(f"map:{key}")
            if window and isinstance(camera, dict):
                window.widget().pending_camera = camera
                window.widget().view.restore_camera(camera)
    for card_id, values in data.get("cards", {}).items():
        if card_id not in controller.card_editors or not isinstance(values, dict):
            continue
        state = controller.card_document_states[card_id]
        for name in ["position", "anchor", "vertical_scroll", "horizontal_scroll",
                     "preview_scroll"]:
            value = values.get(name)
            if type(value) is int and value >= 0:
                setattr(state, name, value)
        if values.get("mode") in [0, 1, 2]:
            state.mode = values["mode"]
        sizes = values.get("splitter_sizes", [])
        if isinstance(sizes, list) and all(type(size) is int and size >= 0 for size in sizes):
            state.splitter_sizes = sizes[:2]
        state.restore(controller.card_editors[card_id])
    panel = controller.window.tree_panel
    expanded = data.get("expanded", [])
    panel.tree_view.collapseAll()
    if isinstance(expanded, list):
        for key in expanded:
            if isinstance(key, str):
                panel.tree_view.setExpanded(panel.tree_model.index_for_card(key), True)
    selected = data.get("selected")
    if isinstance(selected, str):
        try:
            controller.session.select_card(selected)
        except ValueError:
            controller.session.clear_selection()
    else:
        controller.session.clear_selection()
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
