import ast
from pathlib import Path

from lodandsy.application.cards_service import CardsService
from lodandsy.application.entity_session import EntitySession
from lodandsy.application.maps_service import MapsService
from lodandsy.application.project_actions import ProjectActions
from lodandsy.application.tables_service import TablesService
from lodandsy.domain.card import Card
from prototypes.architecture_graph import cycles, dependency_graph

pytest_plugins = ["tests.project_fixture"]


def test_import_boundaries_and_acyclic_graph():
    graph = dependency_graph(Path("lodandsy"))
    assert not cycles(graph)
    feature_ui = {
        "cards": {
            "card_editor",
            "card_document_state",
            "portrait_panel",
            "portrait_crop_dialog",
            "rich_document",
            "rich_toolbar",
            "card_fields",
            "card_creation_dialog",
        },
        "tables": {"table_widget", "table_headers", "table_model", "entity_picker"},
        "maps": {
            "map_widget",
            "map_editor",
            "map_annotations",
            "map_settings_dialogs",
            "map_library",
        },
        "dice": {"dice_widget"},
    }
    for feature in feature_ui:
        foreign = set().union(*(names for key, names in feature_ui.items() if key != feature))
        for role in ("controller", "service"):
            module = f"lodandsy.application.{feature}_{role}"
            for dependency in graph.get(module, ()):
                assert dependency.rsplit(".", 1)[-1] not in foreign, (module, dependency)
                if role == "service":
                    assert ".ui." not in dependency
                for sibling in feature_ui.keys() - {feature}:
                    assert not dependency.startswith(f"lodandsy.application.{sibling}_"), (
                        module,
                        dependency,
                    )
    # Explicit integration allowlist: root/actions/storage/project payload codecs wire built-ins.
    for path in Path("lodandsy/domain").glob("*.py"):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or ""]
            else:
                continue
            assert not any(
                name.startswith(("PySide6", "sqlite3", "lodandsy.ui", "lodandsy.application"))
                for name in imports
            ), path
    for obsolete in [
        "module_session.py",
        "module_controller.py",
        "application_session.py",
        "card_images.py",
    ]:
        assert not (Path("lodandsy/application") / obsolete).exists()


def test_services_without_sibling_ui_and_compound_actions_emit_once(qapp):
    core = EntitySession()
    cards = CardsService(core=core)
    tables = TablesService(core)
    maps = MapsService(core)
    actions = ProjectActions(core, cards, tables, maps)
    document = maps.create_map("Map", Card("resource").id)
    commits = []
    observed = []
    core.committed.connect(lambda: commits.append(1))
    cards.card_created.connect(
        lambda key: observed.append(maps.get_map(document.id).tokens[0].card_id == key)
    )
    token = actions.create_card_placement(document.id, "Card", 10, 20, card_type="character")
    assert commits == [1] and observed == [True]
    assert maps.get_map(document.id).tokens[0] == token
    card = cards.get_card(token.card_id)
    inventory = next(section for section in card.sections if section.purpose == "inventory")
    commits.clear()
    table = actions.section_table(card.id, inventory.id)
    assert commits == [1] and tables.get_table(table.id).id == table.id
    assert actions.section_table(card.id, inventory.id).id == table.id and commits == [1]
    commits.clear()
    actions.delete_entity(card.id)
    assert commits == [1] and not maps.get_map(document.id).tokens


def test_table_commit_updates_only_its_views_without_rebuilding_card(
    project, qtbot, tmp_path, monkeypatch
):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Card", card_type="character")
    inventory = next(s for s in card.sections if s.purpose == "inventory")
    table = app.actions.section_table(card.id, inventory.id)
    app.tables_service.edit_table(table.id, rows=(table.new_row(),))
    editor = app.open_card_editor(card.id).widget()
    editor.select_section(inventory.id)
    standalone = app.tables.open_table(table.id).widget()
    before = editor.table_layout.itemAt(0).widget()
    calls = []
    monkeypatch.setattr(editor, "set_canonical", lambda *args, **kwargs: calls.append(1))
    standalone.model.setData(standalone.model.index(0, 1), "12")
    assert before.model.data(before.model.index(0, 1)) == "12"
    assert editor.table_layout.itemAt(0).widget() is before and not calls
    assert app.tables_service.core is app.maps_service.core is app.cards_service.core
