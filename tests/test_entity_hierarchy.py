import hashlib
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QMessageBox

from lodandsy.application.rich_html import html_text
from lodandsy.application.sqlite_project_store import (
    ProjectError,
    ProjectSnapshot,
    SQLiteProjectStore,
    connect_database,
)
from lodandsy.domain.card import CardPayload
from lodandsy.domain.card_collection import CardCollection
from lodandsy.domain.document_payloads import project_entities
from lodandsy.domain.entity import Entity, EntityCollection
from tests.project_fixture import record_rows, sample_store

pytest_plugins = ["tests.project_fixture"]


def test_mixed_forest_validates_before_changes_and_preserves_payload_identity():
    entities = EntityCollection()
    nodes = [entities.create(kind, kind, object()) for kind in ("card", "map", "table", "card")]
    for parent, child in zip(nodes, nodes[1:]):
        entities.update(child.id, parent_id=parent.id)
    before = entities.summaries()
    payloads = [entities.payload(node.id) for node in nodes]
    for changes in (
        {"parent_id": nodes[-1].id},
        {"parent_id": str(uuid4())},
        {"position": -1},
        {"position": True},
        {"position": 99},
        {"title": ""},
    ):
        with pytest.raises(ValueError):
            entities.update(nodes[0].id, **changes)
        assert entities.summaries() == before
        assert all(entities.payload(n.id) is p for n, p in zip(nodes, payloads))
    entities.update(nodes[2].id, parent_id=None, position=0)
    assert entities.child_ids() == (nodes[2].id, nodes[0].id)
    assert entities.get(nodes[3].id).parent_id == nodes[2].id
    assert entities.delete(nodes[2].id) == (nodes[2].id, nodes[3].id)
    assert entities.get(nodes[0].id).position == 0


def test_mixed_dnd_tool_save_restart_layout_and_subtree_delete(project, tmp_path, monkeypatch):
    app, controller = project
    controller.create_project(tmp_path / "world")
    card = app.create_card("Root")
    other = app.create_card("Keep")
    table = app.modules.session.create_table("Table")
    child = app.create_card("Child", table.id)
    entities, panel = app.session.entities, app.window.tree_panel
    model = panel.tree_model
    assert model.dropMimeData(
        model.mimeData([model.index_for_node(f"table:{table.id}")]),
        Qt.DropAction.MoveAction,
        -1,
        0,
        model.index_for_node("card:" + card.id),
    )
    assert model.dropMimeData(
        model.mimeData([model.index_for_node(f"card:{child.id}")]),
        Qt.DropAction.MoveAction,
        -1,
        0,
        model.index_for_node(f"table:{table.id}"),
    )
    assert not model.canDropMimeData(
        model.mimeData([model.index_for_node("card:" + card.id)]),
        Qt.DropAction.MoveAction,
        -1,
        0,
        model.index_for_node(f"card:{child.id}"),
    )
    assert entities.get(child.id).parent_id == table.id
    editor = app.open_card_editor(other.id).widget()
    editor.text_edit.setPlainText("unsaved text survives unrelated moves")
    app.modules.open_table(table.id)
    dice_widget = app.modules.open_dice().widget()
    dice_widget.counts[20].setValue(0)
    dice_widget.counts[8].setValue(3)
    dice_widget.modifier.setValue(-2)
    assert app.modules.open_dice().widget() is dice_widget
    panel.tree_view.setExpanded(model.index_for_node("card:" + card.id), True)
    panel.tree_view.setExpanded(model.index_for_node(f"table:{table.id}"), True)
    panel.tree_view.setCurrentIndex(model.index_for_node(f"card:{child.id}"))
    assert app.session.current_entity_id == child.id
    assert controller.save_current()
    root = controller.store.root
    controller.create_project(tmp_path / "other", preserve_current=False)
    controller.open_project(root)
    assert app.modules.open_dice().widget().runtime["config"].expression() == "3d8 -2"
    assert app.session.current_entity_id == child.id
    assert panel.current_node_key() == f"card:{child.id}"
    assert panel.tree_view.isExpanded(model.index_for_node("card:" + card.id))
    assert html_text(app.cards.get(other.id).content).strip() == (
        "unsaved text survives unrelated moves"
    )
    assert app.window_manager.find_window("tool:dice") is not None
    messages = []

    def accept(*args, **kwargs):
        messages.append(args[2])
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", accept)
    panel.request_delete(model.index_for_node("card:" + card.id))
    assert "Всего: 3" in messages[0] and "таблиц: 1" in messages[0]
    assert app.session.entities.child_ids() == (other.id,)
    assert app.window_manager.find_window(f"table:{table.id}") is None
    assert app.window_manager.find_window("tool:dice") is not None
    assert app.window_manager.find_window(f"card-editor:{other.id}") is not None
    assert controller.save_current()
    assert controller.store.load().cards == (app.cards.get(other.id),)


def test_payload_and_envelope_inventory_errors_preserve_database(tmp_path):
    store = SQLiteProjectStore.create(tmp_path / "world")
    cards = CardCollection()
    cards.create("Original")
    snapshot = ProjectSnapshot(cards.all(), 1)
    store.save(snapshot)
    with closing(connect_database(store.path)) as c, c:
        c.execute("DELETE FROM card_content")
    original = hashlib.sha256(store.path.read_bytes()).digest()
    with pytest.raises(ProjectError, match="inventory"):
        store.save(replace(snapshot, revision=2))
    assert hashlib.sha256(store.path.read_bytes()).digest() == original
    store.close()


def test_current_map_mixed_dnd_keeps_objects_and_broken_links(project, tmp_path):
    app, controller = project
    legacy = sample_store(tmp_path / "Current world")
    legacy.close()
    controller.open_project(legacy.root)
    entities, panel = app.session.entities, app.window.tree_panel
    model = panel.tree_model
    root, linked_card = app.cards.all()
    document = next(iter(app.modules.session.maps.values()))
    table = next(iter(app.modules.session.tables.values()))
    branch = app.create_card("Branch", table.id)
    for source, parent in (
        (f"map:{document.id}", f"card:{root.id}"),
        (f"table:{table.id}", f"map:{document.id}"),
    ):
        assert model.dropMimeData(
            model.mimeData([model.index_for_node(source)]),
            Qt.DropAction.MoveAction,
            -1,
            0,
            model.index_for_node(parent),
        )
    original_payload = entities.payload(document.id)
    app.open_card_editor(linked_card.id)
    app.modules.open_map(document.id)
    app.session.delete_entity(linked_card.id)
    assert app.window_manager.find_window(f"card-editor:{linked_card.id}") is None
    assert app.window_manager.find_window(f"map:{document.id}") is not None
    assert entities.payload(document.id) != original_payload
    assert not app.modules.session.get_map(document.id).tokens
    assert not model.canDropMimeData(
        model.mimeData([model.index_for_node("card:" + root.id)]),
        Qt.DropAction.MoveAction,
        -1,
        0,
        model.index_for_node(f"card:{branch.id}"),
    )
    assert model.dropMimeData(
        model.mimeData([model.index_for_node(f"card:{branch.id}")]),
        Qt.DropAction.MoveAction,
        -1,
        0,
        QModelIndex(),
    )
    assert model.dropMimeData(
        model.mimeData([model.index_for_node(f"map:{document.id}")]),
        Qt.DropAction.MoveAction,
        -1,
        0,
        model.index_for_node(f"card:{branch.id}"),
    )
    assert entities.get(document.id).parent_id == branch.id
    assert controller.save_current()
    snapshot = controller.store.load()
    assert snapshot.maps == (replace(document, tokens=()),)
    assert snapshot.entity_collection().get(table.id).parent_id == document.id
    archive = tmp_path / "mixed.lodbackup"
    controller.store.backup(archive)
    restored = SQLiteProjectStore.restore(archive, tmp_path / "restored")
    assert restored.load() == snapshot
    restored.close()


def test_search_dispatches_all_document_kinds_and_selection_is_independent(project):
    app, controller = project
    card = app.create_card("Article")
    editor = app.open_card_editor(card.id).widget()
    table = app.modules.session.create_table("Encounter")
    app.modules.session.edit_table(table.id, rows=record_rows(table, ("a searchable wolf",)))
    map_document = app.modules.session.create_map("Guards", str(uuid4()))
    app.open_search()
    dialog = app._search_dialog
    dialog.query.setText("wolf")
    dialog.refresh()
    assert dialog.results.count() == 1
    dialog._open(dialog.results.item(0))
    assert app.window_manager.find_window(f"table:{table.id}") is not None
    dialog.query.setText("guards")
    dialog.refresh()
    dialog._open(dialog.results.item(0))
    assert app.window_manager.find_window(f"map:{map_document.id}") is not None
    assert editor.card_id == card.id
    assert app.window_manager.find_window(f"card-editor:{card.id}").widget() is editor


def test_mixed_envelope_rejects_duplicate_order_unknown_kind_and_missing_parent():
    root, child = str(uuid4()), str(uuid4())
    with pytest.raises(ValueError, match="positions"):
        EntityCollection([(Entity(root, "card", "A", position=1), CardPayload(()))])
    with pytest.raises(ValueError, match="parent"):
        EntityCollection([(Entity(root, "card", "A", child), CardPayload(()))])
    with pytest.raises(ValueError, match="kind"):
        Entity(root, "future", "Future")
    with pytest.raises(ValueError, match="Duplicate"):
        project_entities(cards=(CardCollection().create("C"),) * 2)
