"""Composition root: explicit feature wiring, shared navigation and project lifecycle."""

from html import escape
from types import SimpleNamespace

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QInputDialog, QMessageBox

from lodandsy.application.card_inspector_binding import CardInspectorBinding
from lodandsy.application.cards_controller import CardsController
from lodandsy.application.cards_service import CardsService
from lodandsy.application.clipboard import clipboard_writer
from lodandsy.application.dice_controller import DiceController
from lodandsy.application.economy_service import EconomyService
from lodandsy.application.entity_queries import EntityQueries
from lodandsy.application.entity_session import EntitySession
from lodandsy.application.loot_controller import LootController
from lodandsy.application.maps_controller import MapsController
from lodandsy.application.maps_service import MapsService
from lodandsy.application.media_service import MediaService
from lodandsy.application.project_actions import ProjectActions
from lodandsy.application.project_resources import ProjectResources
from lodandsy.application.shop_controller import ShopController
from lodandsy.application.tables_controller import TablesController
from lodandsy.application.tables_service import TablesService
from lodandsy.domain.actor_state import ActorRef
from lodandsy.domain.card_collection import CardCollection
from lodandsy.domain.card_schema import ACTOR_TYPES, CARD_TYPES
from lodandsy.domain.treasure import CatalogItem
from lodandsy.ui.card_search_dialog import CardSearchDialog
from lodandsy.ui.currency_editor import CurrencyEditor
from lodandsy.ui.entity_picker import EntityPicker
from lodandsy.ui.icons import icon
from lodandsy.ui.rules_editor import RulesEditor
from lodandsy.ui.settings_dialog import SettingsDialog
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
        self.economy = EconomyService(self.core, self.actions.used_denominations, window)
        self.economy.changed.connect(self.cards_service.economy_changed.emit)
        self.tables_service.cell_edit_command = self._table_cell_command
        self.tables_service.cell_caption = self.actions.inventory_activity_caption
        self.tables_service.reference_caption_fields = frozenset({"equipment_kind"})
        self.tables = TablesController(
            window, self.window_manager, self.tables_service, self.open_entity
        )
        self.tables.inventory_owner = self.actions.inventory_owner
        self.tables.window_title = self._table_window_title
        self.tables.set_wallet = self.actions.set_wallet
        self.tables.paste_inventory = self._paste_inventory
        self.economy.changed.connect(self.tables.refresh_economy)
        self.cards_service.actor_changed.connect(self._refresh_actor_inventory_title)
        self.dice = DiceController(self.window_manager)
        tool_dependencies = (
            self.window_manager, lambda: self.resources.store, lambda: self.economy.settings,
            self._tool_catalogue, self._tool_item, lambda key: self.open_entity("card", key),
        )
        self.loot = LootController(*tool_dependencies)
        self.shop = ShopController(*tool_dependencies)
        self.catalogue_tools = (self.loot, self.shop)
        for tool in self.catalogue_tools:
            self.economy.changed.connect(tool.refresh)
            self.cards_service.card_changed.connect(tool.item_changed)
            self.core.entities_deleted.connect(tool.items_deleted)
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
        self.card_views.reference_queries = self.references
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
        self.inspector_binding.open_inventory = self.tables.open_table
        self.inspector_binding.open_sheet = self.card_views.open_game_sheet
        self.card_views.placements_query = self.actions.actor_placements
        self.card_views.locate_placement = self.maps.focus_token
        self.card_views.delete_actor = self.actions.delete_actor

        def show_map_panel(widget):
            if window.inspector_panel.pages.currentWidget() is not widget:
                self.inspector_binding.finish_edits()
                window.inspector_panel.show_feature_page(widget)

        self.maps.show_inspector_page = show_map_panel
        self.maps.show_inspector_control = window.inspector_panel.show_context_control
        self.maps.choose_note_target = self._choose_map_note_target
        self.maps.open_note_target = self._open_map_note_target
        self.maps.note_target_info = self._map_note_target_info
        self.maps.token_card_types = tuple((kind, info.title) for kind, info in CARD_TYPES.items())
        self.maps.choose_token_actor = self._choose_token_actor
        self.maps.show_actor = lambda card, actor, scale=None: self.inspector_binding.show_actor(
            ActorRef(card, actor), feet_per_cell=scale
        )
        self.maps.update_actor_scale = lambda card, actor, scale: (
            self.inspector_binding.update_actor_scale(ActorRef(card, actor), scale)
        )
        self.window_manager.active_window_changed.connect(self._refresh_map_inspector)
        self.maps.inspector_context_changed.connect(self._map_inspector_changed)
        self.settings_window = None
        self.maps.open_participant = self.card_views.open_game_sheet
        self.maps.open_participant_inventory = self._open_participant_inventory
        self.rules_action = QAction("Игровая система и правила…", window)
        self.rules_action.setEnabled(False)
        self.rules_action.triggered.connect(self.open_rules)
        self.economy_action = QAction("Экономика проекта…", window)
        self.economy_action.setIcon(icon("coins"))
        self.economy_action.setEnabled(False)
        self.economy_action.triggered.connect(self.open_economy)
        window.right_rail.settings_button.clicked.connect(lambda: self.open_settings())
        self.core.replaced.connect(self.close_settings)
        self.maps_service.placements_changed.connect(self._placements_changed)
        self.maps_service.map_deleted.connect(self._placements_changed)
        self.navigator_selection = None
        tree = window.tree_panel
        tree.deletion_reference_count = self.maps_service.placement_count
        tree.deletion_details = self.actions.deletion_details
        tree.entity_selected.connect(self._on_navigator_selected)
        tree.entity_open_requested.connect(self.open_entity)
        tree.create_requested.connect(self._on_create_requested)
        tree.typed_create_requested.connect(self._on_create_requested)
        tree.folder_create_requested.connect(self.create_folder)
        tree.player_create_requested.connect(
            lambda title, parent, kind: self._on_create_requested(title, parent, kind, player=True)
        )
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
        self.maps_service.map_destination_changed.connect(self._module_title_changed)
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

    def _table_cell_command(self, key, row_id, column_id, value, *, expected, parsed):
        table = self.tables_service.get_table(key)
        column = next(c for c in table.columns if c.id == column_id)
        if not parsed or column.key != "active" or self.actions.inventory_owner(key) is None:
            return NotImplemented
        row = next(r for r in table.rows if r.id == row_id)
        if row.value(column_id) != expected and row.value(column_id) != value:
            return self.tables_service.set_cell(
                key, row_id, column_id, value, expected=expected, parsed=True
            )
        guard = self.core.generation, self.core.serial
        conflicts = self.actions.equipment_conflicts(key, row_id) if value is True else ()
        if conflicts:
            names = ", ".join(name for _, name in conflicts)
            answer = QMessageBox.question(
                self.window,
                "Заменить экипировку?",
                f"Уже надето: {names}. Снять и надеть выбранный предмет?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return self.tables_service.get_table(key)
        return self.actions.set_inventory_activity(
            key, row_id, value, replace_existing=bool(conflicts), expected=guard
        )

    def _paste_inventory(self, key, transfer):
        store = self.resources.store
        if store is None:
            raise ValueError("Сначала откройте проект")
        guard = self.core.generation, self.core.serial
        before, candidate, coins = self.actions.plan_inventory_paste(
            key, transfer, store.project_id
        )
        if coins:
            currency = self.economy.currency
            caption = ", ".join(currency.price_text(coin) for coin in coins)
            total = currency.total_text(sum(currency.value(coin) for coin in coins))
            prompt = (
                f"В инвентарь «{before.title}» будут добавлены монеты: {caption} ({total}).\n"
                f"Новых строк предметов: {len(candidate.rows) - len(before.rows)}."
            )
            answer = QMessageBox.question(
                self.window, "Добавить в инвентарь?", prompt,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return None
            if store is not self.resources.store or guard != (
                self.core.generation, self.core.serial
            ):
                raise ValueError("Проект изменился. Повторите вставку.")
        self.tables_service.update_table(candidate, expected=before)
        self.window.show_notice("Набор добавлен в инвентарь")

    def ensure_project(self):
        return self.resources.store is not None or (
            self.project_controller is not None and self.project_controller.save_current()
        )

    def attach_project(self, project):
        self.project_controller = project

    def open_card_editor(self, key):
        return self.card_views.open_card_editor(key)

    def create_card(self, title, parent_id=None, *, card_type="note", player=False):
        with self.core.transaction():
            card = self.cards_service.create_card(title, parent_id, card_type=card_type)
            if player:
                self.cards_service.set_player(card.id, True, create=True)
        return self.cards_service.get_card(card.id)

    def create_folder(self, parent_id=None):
        entities = self.core.entities
        occupied = {entities.get(key).title.casefold() for key in entities.child_ids(parent_id)}
        base = title = "Новая папка"
        suffix = 2
        while title.casefold() in occupied:
            title = f"{base} {suffix}"
            suffix += 1
        folder = self.create_card(title, parent_id, card_type="folder")
        self.core.select(folder.id)
        self.window.tree_panel.edit_folder(folder.id)
        return folder

    def _choose_map_note_target(self, map_id, previous=None):
        generation = self.core.generation
        choices = ("Текстовая заметка", "Инвентарь")
        choice, accepted = QInputDialog.getItem(
            self.window, "Заметка на карте", "Содержимое", choices,
            int(previous is not None and previous.target_kind == "inventory"), False,
        )
        if not accepted or generation != self.core.generation:
            return None
        inventory = choice == choices[1]
        kind = "inventory" if inventory else "note"
        picker = EntityPicker(
            self.references,
            SimpleNamespace(ref_kind="table" if inventory else "card",
                            ref_card_type=None if inventory else "note"),
            self.window,
            current=previous.target_id if previous and previous.target_kind == kind else None,
            predicate=self.actions.inventory_owner if inventory else None,
            click=True,
            create_label=None if inventory else "Создать заметку…",
        )
        picker.setWindowTitle("Выбрать инвентарь" if inventory else "Выбрать заметку")
        result = picker.exec()
        key = picker.chosen_id
        picker.deleteLater()
        if not result or generation != self.core.generation:
            return None
        if result == EntityPicker.CREATE and not inventory:
            title, accepted = QInputDialog.getText(self.window, "Новая заметка", "Название")
            if (not accepted or not title.strip() or generation != self.core.generation
                    or self.maps_service.find_map(map_id) is None):
                return None
            key = self.create_card(title, card_type="note").id
        return (kind, key) if self._map_note_target_info(kind, key) is not None else None

    def _choose_token_actor(self, card):
        if card.card_type not in ACTOR_TYPES or not card.actors or card.default_actor_id:
            return None, True
        actors = [(actor.id, f"{actor.name} · {actor.id[:8]}") for actor in card.actors]
        if not card.value("player"):
            actors.insert(0, (None, "Новый участник"))
        labels = [label for _, label in actors]
        label, accepted = QInputDialog.getItem(
            self.window, "Участник", "Кого разместить", labels, 0, False,
        )
        return (actors[labels.index(label)][0], True) if accepted else (None, False)

    def _map_note_target_info(self, kind, key):
        if kind == "inventory":
            target = self.references.resolve(key, kind="table")
            return target if target and self.actions.inventory_owner(key) is not None else None
        return self.references.resolve(key, kind="card", card_type="note")

    def _open_map_note_target(self, kind, key):
        if self._map_note_target_info(kind, key) is None:
            self.window.show_notice("Документ заметки удалён или недоступен. Измените привязку.")
            return None
        if kind == "inventory":
            return self.tables.open_table(key, floating=True)
        self.open_card_editor(key)
        return self.window_manager.focus_window(self.card_editor_window_key(key), floating=True)

    def open_settings(self, section=None):
        project = self.resources.store
        controller = self.project_controller
        if project is None or controller is None:
            self.window.show_notice("Сначала создайте или откройте проект")
            return None
        if self.settings_window is None:
            generation = self.core.generation

            def apply_economy(previous, currency, categories):
                if project is not self.resources.store or generation != self.core.generation:
                    raise ValueError("Проект изменился. Откройте его настройки заново.")
                wallet_drafts = {address[1] for address in self.tables.wallet_edits.drafts}
                previous.currency.validate_change(currency, wallet_drafts)
                self.economy.apply_settings(previous, currency, categories)

            economy = CurrencyEditor(
                self.economy.settings,
                self.economy.used_denominations(),
                apply_economy,
            )
            self.settings_window = SettingsDialog(
                project.root.name, RulesEditor(self.cards_service), economy,
                controller.backup_action, controller.restore_action, self.window,
            )
            self.settings_window.finished.connect(lambda _: setattr(self, "settings_window", None))
        dialog = self.settings_window
        if section is not None:
            dialog.select_section(section)
        if dialog.isMinimized():
            dialog.showNormal()
        else:
            dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def open_rules(self):
        dialog = self.open_settings("rules")
        return dialog.rules if dialog is not None else None

    def open_economy(self):
        dialog = self.open_settings("currency")
        return dialog.economy if dialog is not None else None

    def may_close_settings(self):
        return self.settings_window is None or self.settings_window.may_close()

    def close_settings(self):
        if self.settings_window is not None:
            self.settings_window.close_confirmed()

    def _placements_changed(self, map_id):
        for key in self.card_views.opened_ids:
            self.card_views.refresh_relations(key)

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

    def _table_window_title(self, document):
        owner = self.actions.inventory_owner(document.id)
        if isinstance(owner, ActorRef):
            return f"Инвентарь — {self.cards_service.get_actor(owner).name}"
        return document.title

    def _refresh_actor_inventory_title(self, card_id, actor_id, fields):
        if "name" not in fields:
            return
        try:
            actor = self.cards_service.get_actor(ActorRef(card_id, actor_id))
        except ValueError:
            return
        if actor.inventory_id is not None:
            self.tables.refresh_title(actor.inventory_id)

    def _open_participant_inventory(self, card_id, actor_id):
        try:
            actor = self.cards_service.get_actor(ActorRef(card_id, actor_id))
            if actor.inventory_id is not None:
                return self.tables.open_table(actor.inventory_id, floating=True)
        except ValueError:
            pass
        self.window.show_notice("Инвентарь участника недоступен.")

    def replace_cards(self, cards):
        self.close_settings()
        self.reset_catalogue_tools()
        for key in self.window_manager.window_keys():
            if key != "tool:dice":
                self.window_manager.close_window(key)
        self.cards_service.replace_cards(cards)

    def reset_catalogue_tools(self):
        for tool in self.catalogue_tools:
            tool.reset()

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
        collection = self.core.entities
        entities = collection.summaries()
        card_types = {
            entity.id: collection.payload(entity.id).card_type
            for entity in entities if entity.kind == "card"
        }
        self.window.tree_panel.set_entities(entities, card_types=card_types)

    def shutdown_features(self):
        self.close_settings()
        self.maps.shutdown()
        self.media.shutdown()

    def flush_edits(self):
        self.card_views.flush_edits()
        self.tables_service.flush_edits()
        self.tables.wallet_edits.flush()
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

    def _refresh_map_inspector(self, window_key):
        if not self.maps.show_inspector_context(window_key):
            self.inspector_binding.clear_map_context()

    def _map_inspector_changed(self, map_id):
        key = "map:" + map_id
        if self.window_manager.active_window_key == key and self.window_manager.find_window(key):
            self._refresh_map_inspector(key)

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
        for tool in self.catalogue_tools:
            if key == tool.key:
                return tool.open()
        raise ValueError("Неподдерживаемый документ")

    @staticmethod
    def _catalogue_entry(card):
        return CatalogItem(
            card.id, card.title, card.value("item_category"), card.value("cost"),
            card.value("weight"), card.value("loot_enabled"),
        )

    def _tool_catalogue(self):
        return (
            self._catalogue_entry(card) for card in self.cards.all() if card.card_type == "item"
        )

    def _tool_item(self, key):
        try:
            card = self.cards.get(key)
        except ValueError:
            return None
        return self._catalogue_entry(card) if card.card_type == "item" else None

    def copy_card_link(self, entity_id):
        entity = self.core.entities.get(entity_id)
        uri = f"lodandsy://entity/{entity.id}"
        clipboard_writer().copy(uri, html=f'<a href="{uri}">{escape(entity.title)}</a>')

    def _on_create_requested(
        self,
        title: str,
        parent_id: object,
        card_type="note",
        player=False,
    ) -> None:
        resolved_parent_id = self._optional_card_id(parent_id)

        self.create_card(
            title,
            resolved_parent_id,
            card_type=card_type,
            player=player,
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
