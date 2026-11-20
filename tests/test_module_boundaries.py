from pathlib import Path

import pytest

from lodandsy.application.cards_service import CardsService
from lodandsy.application.entity_session import EntitySession
from lodandsy.application.maps_service import MapsService
from lodandsy.application.project_actions import ProjectActions
from lodandsy.application.tables_service import TablesService
from lodandsy.domain.card import Card
from prototypes.architecture_graph import cycles, dependency_graph, module_imports, module_paths

pytest_plugins = ["tests.project_fixture"]


def modules(layer, names):
    return {f"lodandsy.{layer}.{name}" for name in names.split()}


# Every runtime file has an explicit owner; a new helper cannot silently escape the gate.
FEATURES = {
    "cards": modules("domain", "card card_collection card_schema")
    | modules(
        "application",
        "cards_controller cards_service card_editor_binding card_inspector_binding "
        "card_media_controller card_payload_codec rich_html rich_text_codec",
    )
    | modules(
        "ui",
        "card_editor card_document_state card_fields card_creation_dialog card_search_dialog "
        "portrait_panel portrait_crop_dialog rich_document rich_toolbar",
    ),
    "tables": modules("domain", "table_document")
    | modules("application", "tables_controller tables_service table_column_codec")
    | modules("ui", "table_widget table_headers table_model"),
    "maps": modules("domain", "map_document map_fog")
    | modules(
        "application",
        "maps_controller maps_service map_pyramid map_pyramid_worker map_tiles fog_geometry",
    )
    | modules(
        "ui",
        "map_widget map_editor map_annotations map_settings_dialogs map_library "
        "map_presentation fog_tools",
    ),
    "dice": modules("domain", "dice")
    | modules("application", "dice_controller")
    | modules("ui", "dice_widget"),
}
SHARED = (
    {"lodandsy", "lodandsy.domain", "lodandsy.application", "lodandsy.ui"}
    | modules("domain", "entity entity_reference module_values")
    | modules(
        "application",
        "entity_session entity_queries field_edits edit_conflict background_tasks clipboard "
        "resource_paths project_resources media_service project_history",
    )
    | modules(
        "ui",
        "entity_picker semantic_edits conflict_bar icons project_tree_model card_tree_view "
        "navigator_actions window_manager workspace_host workspace_placement fixed_panel_host "
        "left_rail right_rail theme project_chooser",
    )
)
# Built-in composition, project persistence/codecs and fixed shell adapters deliberately wire
# modules. These are not neutral helpers that feature code may import without a declared edge.
INTEGRATION = (
    {"lodandsy.main"}
    | modules("domain", "document_payloads")
    | modules(
        "application",
        "app_controller project_actions project_controller save_coordinator sqlite_project_store "
        "workspace_state",
    )
    | modules("ui", "app_shell inspector_panel tree_panel")
)
INTEGRATION_EDGES = {
    ("lodandsy.domain.card_collection", "lodandsy.domain.document_payloads"),
    ("lodandsy.application.card_inspector_binding", "lodandsy.ui.inspector_panel"),
    ("lodandsy.ui.window_manager", "lodandsy.ui.app_shell"),
}
# Token overrides validate a stored built-in Card type, without depending on Card operations/UI.
TYPE_CONTRACT = ("lodandsy.domain.map_document", "lodandsy.domain.card_schema")
OWNERS = {name: owner for owner, names in FEATURES.items() for name in names}
OWNERS.update(dict.fromkeys(SHARED, "shared"))


def boundary_violations(graph):
    violations = []
    for origin in graph.keys() - INTEGRATION:
        pending, seen = [(origin,)], set()
        while pending:
            path = pending.pop()
            source = path[-1]
            if source in seen:
                continue
            seen.add(source)
            for target in graph.get(source, ()):
                edge = source, target
                route = (*path, target)
                if target in INTEGRATION:
                    if edge not in INTEGRATION_EDGES:
                        violations.append(route)
                    continue
                if edge == TYPE_CONTRACT:
                    continue
                owner = OWNERS.get(target)
                if owner not in {"shared", OWNERS.get(origin)}:
                    violations.append(route)
                else:
                    pending.append(route)
    return violations


def dependencies(graph, origin):
    pending, seen = list(graph[origin]), set()
    while pending:
        target = pending.pop()
        if target not in seen:
            seen.add(target)
            pending.extend(graph.get(target, ()))
    return seen


def test_import_boundaries_and_acyclic_graph():
    root = Path(__file__).resolve().parents[1] / "lodandsy"
    paths, graph = module_paths(root), dependency_graph(root)
    assigned = [*SHARED, *INTEGRATION, *(name for names in FEATURES.values() for name in names)]
    assert len(assigned) == len(set(assigned)), "A module has multiple owners"
    assert set(paths) == set(assigned), "Classify new/deleted runtime modules explicitly"
    assert not cycles(graph)
    assert not boundary_violations(graph)
    for name, path in paths.items():
        imports = module_imports(name, path)
        if name.startswith("lodandsy.domain."):
            assert not any(
                target.startswith(
                    ("PySide6", "PySide6QtAds", "shiboken6", "sqlite3", "lodandsy.ui",
                     "lodandsy.application")
                )
                for target in imports
            ), name
        if name.startswith("lodandsy.application.") and name not in INTEGRATION:
            if not name.endswith(("_controller", "_binding")):
                assert not any(".ui." in target for target in dependencies(graph, name)), name
    # The one cross-domain edge is constrained to the declared type catalogue symbol.
    imports = module_imports(TYPE_CONTRACT[0], paths[TYPE_CONTRACT[0]])
    assert {name for name in imports if name.startswith(TYPE_CONTRACT[1] + ".")} == {
        TYPE_CONTRACT[1] + ".CARD_TYPES"
    }
    for obsolete in [
        "module_session.py",
        "module_controller.py",
        "application_session.py",
        "card_images.py",
    ]:
        assert not (Path("lodandsy/application") / obsolete).exists()


@pytest.mark.parametrize(
    "source,statement,target",
    [
        ("ui.fog_tools", "from .rich_toolbar import RichToolbar", "ui.rich_toolbar"),
        ("ui.map_presentation", "from . import table_model as model", "ui.table_model"),
        ("ui.rich_document", "import lodandsy.ui.dice_widget as dice", "ui.dice_widget"),
        ("ui.table_model", "from ..application import map_tiles", "application.map_tiles"),
        ("ui.dice_widget", "from lodandsy.domain import map_fog", "domain.map_fog"),
        ("application.fog_geometry", "from .tables_service import TablesService",
         "application.tables_service"),
        ("application.card_media_controller", "from .app_controller import AppController",
         "application.app_controller"),
    ],
)
def test_boundary_gate_rejects_helper_imports_including_relative(
    tmp_path, source, statement, target
):
    root = tmp_path / "lodandsy"
    for name, text in ((source, f"def deferred():\n    {statement}\n"), (target, "")):
        path = root.joinpath(*name.split(".")).with_suffix(".py")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    graph = dependency_graph(root)
    assert graph["lodandsy." + source] == ["lodandsy." + target]
    assert boundary_violations(graph)


def test_boundary_gate_rejects_transitive_leak_through_shared_helper():
    graph = {
        "lodandsy.application.maps_controller": ["lodandsy.application.background_tasks"],
        "lodandsy.application.background_tasks": ["lodandsy.ui.table_model"],
        "lodandsy.ui.table_model": [],
    }
    assert (
        "lodandsy.application.maps_controller",
        "lodandsy.application.background_tasks",
        "lodandsy.ui.table_model",
    ) in boundary_violations(graph)


def test_relative_package_reexports_are_resolved_without_importing(tmp_path):
    root = tmp_path / "lodandsy"
    package = root / "ui"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("from . import fog_tools as fog", encoding="utf-8")
    (package / "fog_tools.py").write_text(
        "raise RuntimeError('must not execute')", encoding="utf-8"
    )
    graph = dependency_graph(root)
    assert "lodandsy.ui.fog_tools" in graph["lodandsy.ui"]
    assert not cycles(graph)


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
