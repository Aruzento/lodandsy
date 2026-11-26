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
    store = controller.resources.store
    return {
        "version": 4,
        "documents": list(controller.window_manager.window_keys()),
        "active": controller.window_manager.active_window_key,
        "entity_selected": controller.core.selected_id,
        "navigator_selected": panel.current_node_key(),
        "navigator_expanded": panel.expanded_keys(),
        "navigator_scroll": panel.tree_view.verticalScrollBar().value(),
        "cards": controller.card_views.capture_ui(),
        **controller.maps.capture_ui(),
        "tables": controller.tables.capture_ui(),
        "economy_tools": {
            "project_id": store.project_id if store is not None else None,
            "loot": controller.loot.capture(),
            "shop": controller.shop.capture(),
        },
        "panel_widths": controller.window.panel_widths(),
        "geometry": base64.b64encode(bytes(controller.window.saveGeometry())).decode("ascii"),
        "chrome": base64.b64encode(bytes(controller.window.saveState(1))).decode("ascii"),
        "layout": base64.b64encode(bytes(controller.window.workspace.saveState(1))).decode("ascii"),
    }


def restore_workspace(controller, data):
    if not isinstance(data, dict) or data.get("version") != 4:
        raise ValueError("Неподдерживаемая версия раскладки")
    documents = data.get("documents")
    if not isinstance(documents, list) or not all(isinstance(key, str) for key in documents):
        raise ValueError("Повреждён список документов раскладки")
    geometry = base64.b64decode(data.get("geometry", ""), validate=True)
    layout = base64.b64decode(data.get("layout", ""), validate=True)
    chrome = base64.b64decode(data.get("chrome", ""), validate=True)
    tools = data.get("economy_tools")
    store = controller.resources.store
    if (
        store is not None
        and isinstance(tools, dict)
        and tools.get("project_id") == store.project_id
    ):
        controller.loot.restore(tools.get("loot"))
        controller.shop.restore(tools.get("shop"))
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
    widths = data.get("panel_widths", {})
    if isinstance(widths, dict):
        controller.window.restore_panel_widths(widths)
    feature_maps = {
        name: values
        for name in ("maps", "map_editors")
        if isinstance(values := data.get(name, {}), dict)
    }
    controller.maps.restore_ui(feature_maps)
    if isinstance(tables := data.get("tables", {}), dict):
        controller.tables.restore_ui(tables)
    saved = data.get("cards", {})
    if not isinstance(saved, dict):
        raise ValueError("Повреждён список настроек карточек")
    controller.card_views.restore_ui(saved)
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
            controller.core.select(selected)
        except ValueError:
            controller.core.select(None)
    else:
        controller.core.select(None)
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
