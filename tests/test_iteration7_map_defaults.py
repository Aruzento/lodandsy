from dataclasses import replace
from uuid import uuid4

from lodandsy.domain.map_document import MapGrid
from tests.project_fixture import map_services

pytest_plugins = ["tests.project_fixture"]


def test_defaults_and_one_time_layer_initialization(qapp):
    service, *_ = map_services()
    document = service.create_map("Map", str(uuid4()))
    assert MapGrid().opacity == 0.25
    assert len(document.layers) == 1 and document.layers[0].visible
    assert document.layers[0].title == "Слой 1"
    service.delete_layer(document.id, document.layers[0].id)
    service.initialize_layers(document.id)
    assert not service.get_map(document.id).layers
    service.undo_stack(document.id).undo()
    assert service.get_map(document.id).layers == document.layers
    service._put_map(replace(document, layers=(), layers_initialized=False))
    service.initialize_layers(document.id)
    initialized = service.get_map(document.id)
    assert len(initialized.layers) == 1
    service.initialize_layers(document.id)
    assert service.get_map(document.id) == initialized


def test_token_context_without_actor_keeps_inventory_action_disabled(
    project, tmp_path, qtbot, monkeypatch
):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QMenu

    from tests.test_map_tokens_grid import open_map

    app, project = project
    document, viewer = open_map(app, project, tmp_path, qtbot)
    card = app.create_card("Card")
    app.maps_service.add_token(document.id, card.id, 50, 50)
    app.maps_service.add_token(document.id, card.id, 100, 100)
    actions = []

    class InspectMenu(QMenu):
        def exec(self, _point):
            actions.extend((action.text(), action.isEnabled()) for action in self.actions())
            return self.actions()[-1]

    class Event:
        def screenPos(self):
            return QPoint(0, 0)

        def accept(self):
            pass

    monkeypatch.setattr("lodandsy.ui.map_annotations.QMenu", InspectMenu)
    viewer.view._tokens[0].contextMenuEvent(Event())
    assert actions == [
        ("Открыть карточку", True),
        ("Открыть инвентарь", False),
        ("Копировать токен", True),
        ("Показать картинку", True),
        ("Удалить токен", True),
    ]
    assert app.cards.get(card.id)
    assert len(app.maps_service.get_map(document.id).tokens) == 1
