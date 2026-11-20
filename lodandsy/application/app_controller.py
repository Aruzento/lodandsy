"""Composition root: explicit feature wiring, shared navigation and project lifecycle."""

from html import escape

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QInputDialog

from lodandsy.application.card_inspector_binding import CardInspectorBinding
from lodandsy.application.cards_controller import CardsController
from lodandsy.application.cards_service import CardsService
from lodandsy.application.clipboard import clipboard_writer
from lodandsy.application.dice_controller import DiceController
from lodandsy.application.entity_queries import EntityQueries
from lodandsy.application.entity_session import EntitySession
from lodandsy.application.maps_controller import MapsController
from lodandsy.application.maps_service import MapsService
from lodandsy.application.media_service import MediaService
from lodandsy.application.project_actions import ProjectActions
from lodandsy.application.project_resources import ProjectResources
from lodandsy.application.tables_controller import TablesController
from lodandsy.application.tables_service import TablesService
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.card_search_dialog import CardSearchDialog
from lodandsy.ui.window_manager import WindowManager


class AppController:
    def __init__(self, window, cards=None):
        self.window = window
        clipboard_writer().message.connect(window.show_notice)
        self.project_controller = None
        collection = cards if cards is not None else CardCollection()
        self.core = EntitySession(collection.entities, window)
        self.resources = ProjectResources(self.core, window)
        self.cards_service = CardsService(collection, window, core=self.core)
        self.references = EntityQueries(
            self.core,
            self.cards_service.reference_info,
            window,
            type_options=self.cards_service.reference_types(),
            field_options=self.cards_service.projection_fields(),
        )
        self.cards_service.card_changed.connect(self.references.refresh)
        self.tables_service = TablesService(self.core, window, references=self.references)
        self.maps_service = MapsService(self.core, window)
        self.window_manager = WindowManager(window)
        self.media = MediaService(self.resources, window, window.show_notice)
        self.actions = ProjectActions(
            self.core, self.cards_service, self.tables_service, self.maps_service
        )
        self.tables = TablesController(
            window, self.window_manager, self.tables_service, self.open_entity
        )
        self.dice = DiceController(self.window_manager)
        self.card_views = CardsController(
            window,
            self.window_manager,
            self.cards_service,
            self.resources,
            self.media,
            self.tables.embedded_view,
            self.actions.section_table,
            self.open_entity,
            self.copy_card_link,
            self.ensure_project,
        )
        self.maps = MapsController(
            window,
            self.window_manager,
            self.maps_service,
            self.cards_service,
            self.resources,
            self.media,
            self.actions,
            self.open_card_editor,
            self.ensure_project,
            self.card_views.request_card_creation,
            self.references,
        )
        self.inspector_binding = CardInspectorBinding(
            self.cards_service,
            window.inspector_panel,
            self.actions.update_entity,
            self.actions.title_edits,
        )
        self.navigator_selection = None
        tree = window.tree_panel
        tree.deletion_reference_count = self.maps_service.placement_count
        tree.entity_selected.connect(self._on_navigator_selected)
        tree.entity_open_requested.connect(self.open_entity)
        tree.create_requested.connect(self._on_create_requested)
        tree.typed_create_requested.connect(self._on_create_requested)
        tree.rename_requested.connect(self.rename_card)
        tree.delete_requested.connect(self.delete_card)
        tree.reparent_requested.connect(self._on_reparent_requested)
        tree.move_requested.connect(self._on_move_requested)
        tree.copy_link_requested.connect(self.copy_card_link)
        tree.move_parent_requested.connect(self.request_move_card)
        tree.map_editor_requested.connect(self.maps.open_map_editor)
        tree.module_create_requested.connect(self.request_create)
        tree.module_rename_requested.connect(self.request_rename)
        tree.module_delete_requested.connect(self.request_delete)
        self.maps.busy_changed.connect(
            lambda: tree.set_map_creation_enabled(not self.maps.importing)
        )
        self.core.entity_created.connect(lambda key: self.refresh_tree())
        self.core.entities_deleted.connect(lambda keys: self.refresh_tree())
        self.core.entity_changed.connect(
            lambda key, fields: (
                self.refresh_tree() if fields & {"title", "parent_id", "position"} else None
            )
        )
        self.core.replaced.connect(self.refresh_tree)
        self.core.selection_changed.connect(self._on_selected_entity_changed)
        self.maps_service.map_changed.connect(self._module_title_changed)
        self.tables_service.table_changed.connect(
            lambda key, change: self._module_title_changed(key) if change.title else None
        )
        self._search_dialog = None
        search = QAction("Найти документ…", window)
        search.setShortcut(QKeySequence.StandardKey.Find)
        search.triggered.connect(self.open_search)
        window.addAction(search)
        tree.search_requested.connect(self.open_search)
        self.refresh_tree()

    @property
    def cards(self):
        return self.cards_service.cards

    @property
    def project_root(self):
        return self.resources.root

    @staticmethod
    def card_editor_window_key(key):
        return f"card-editor:{key}"

    def ensure_project(self):
        return self.resources.store is not None or (
            self.project_controller is not None and self.project_controller.save_current()
        )

    def attach_project(self, project):
        self.project_controller = project

    def open_card_editor(self, key):
        return self.card_views.open_card_editor(key)

    def create_card(self, title, parent_id=None, *, card_type="note"):
        return self.cards_service.create_card(title, parent_id, card_type=card_type)

    def rename_card(self, key, title):
        return self.actions.update_entity(key, title=title)

    def reparent_card(self, key, parent_id):
        return self.actions.update_entity(key, parent_id=parent_id)

    def delete_card(self, key):
        return self.actions.delete_entity(key)

    def follow_link(self, url, editor):
        return self.card_views.follow_link(url, editor)

    def set_project_root(self, root):
        self.resources.root = root
        self.media.invalidate()
        self.card_views.set_project_root(root)

    def replace_cards(self, cards):
        for key in self.window_manager.window_keys():
            if key != "tool:dice":
                self.window_manager.close_window(key)
        self.cards_service.replace_cards(cards)

    def request_create(self, kind, parent_id=None):
        if kind == "map":
            return self.maps.request_map(parent_id)
        if kind == "table":
            return self.tables.request_table(parent_id)
        raise ValueError("Unsupported module kind")

    def request_rename(self, kind, key):
        entity = self.core.entities.get(key)
        title, ok = QInputDialog.getText(
            self.window, "Переименование", "Название:", text=entity.title
        )
        if ok and title.strip():
            self.actions.update_entity(key, title=title)

    def request_delete(self, kind, key):
        panel = self.window.tree_panel
        panel.request_delete(panel.tree_model.index_for_node(f"{kind}:{key}"))

    def _module_title_changed(self, key):
        entity = self.core.entities.get(key)
        reference = self.references.info(key)
        if reference is not None and reference.title != entity.title:
            self.references.refresh(key, frozenset({"title"}))
        model = self.window.tree_panel.tree_model
        index = model.index_for_node(f"{entity.kind}:{key}")
        if index.isValid() and index.data() == entity.title:
            return
        self.window.tree_panel.tree_model.set_title(key, entity.title)
        if self.core.selected_id == key:
            self.inspector_binding.refresh()
        if self._search_dialog is not None:
            self._search_dialog.refresh()

    def refresh_tree(self):
        self.window.tree_panel.set_entities(self.core.entities.summaries())

    def shutdown_features(self):
        self.maps.shutdown()
        self.media.shutdown()

    def flush_edits(self):
        self.card_views.flush_edits()
        self.tables_service.flush_edits()
        self.actions.title_edits.flush()

    def open_entity(self, kind, entity_id):
        entity = self.core.entities.get(entity_id)
        if entity.kind != kind:
            raise ValueError("Тип документа не соответствует ID")
        keys = {"card": "card-editor:", "map": "map:", "table": "table:"}
        if kind not in keys:
            raise ValueError("Неподдерживаемый объект навигации")
        return self.open_document(keys[kind] + entity_id)

    def request_move_card(self, card_id):
        card = self.core.entities.get(card_id)
        excluded = {card_id, *self.core.entities.descendant_ids(card_id)}
        choices = [
            (None, "Корень проекта"),
            *(
                (item.id, f"{item.title} · {item.kind}")
                for item in self.core.entities.summaries()
                if item.id not in excluded
            ),
        ]
        labels = [label for _key, label in choices]
        selected = next((i for i, (key, _label) in enumerate(choices) if key == card.parent_id), 0)
        label, accepted = QInputDialog.getItem(
            self.window, "Переместить документ", "Родитель:", labels, selected, False
        )
        if accepted:
            self.reparent_card(card_id, choices[labels.index(label)][0])

    def _on_navigator_selected(self, kind, entity_id):
        self.core.select(entity_id)

    def _on_selected_entity_changed(self, entity_id):
        entity = self.cards_service.current_entity
        self.navigator_selection = f"{entity.kind}:{entity.id}" if entity else None
        self.window.tree_panel.select_node(self.navigator_selection)

    def open_search(self):
        if self._search_dialog is None:
            self._search_dialog = CardSearchDialog(self.cards_service, self.window)
            self._search_dialog.entity_open_requested.connect(self.open_entity)
        self._search_dialog.show()
        self._search_dialog.raise_()
        self._search_dialog.activateWindow()
        self._search_dialog.query.setFocus()

    def open_document(self, key: str):
        prefix = "card-editor:"
        if key.startswith(prefix):
            return self.open_card_editor(key[len(prefix) :])
        if key.startswith("map-editor:"):
            return self.maps.open_map_editor(key[11:])
        if key.startswith("map:"):
            return self.maps.open_map(key[4:])
        if key.startswith("table:"):
            return self.tables.open_table(key[6:])
        if key == "tool:dice":
            return self.dice.open()
        raise ValueError("Неподдерживаемый документ")

    def copy_card_link(self, entity_id):
        entity = self.core.entities.get(entity_id)
        uri = f"lodandsy://entity/{entity.id}"
        clipboard_writer().copy(uri, html=f'<a href="{uri}">{escape(entity.title)}</a>')

    def _on_create_requested(
        self,
        title: str,
        parent_id: object,
        card_type="note",
    ) -> None:
        resolved_parent_id = self._optional_card_id(parent_id)

        self.create_card(
            title,
            resolved_parent_id,
            card_type=card_type,
        )

    def _on_move_requested(self, card_id: str, parent_id: object, position: int) -> None:
        self.actions.update_entity(
            card_id, parent_id=self._optional_card_id(parent_id), position=position
        )

    def _on_reparent_requested(
        self,
        card_id: str,
        parent_id: object,
    ) -> None:
        resolved_parent_id = self._optional_card_id(parent_id)

        self.reparent_card(
            card_id,
            resolved_parent_id,
        )

    @staticmethod
    def _optional_card_id(
        value: object,
    ) -> str | None:
        if value is None:
            return None

        if isinstance(
            value,
            str,
        ):
            return value

        raise TypeError("Card id must be str or None")
