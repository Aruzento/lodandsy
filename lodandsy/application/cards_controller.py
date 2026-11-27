"""Cards editor/document lifecycle over public services and an injected Table view factory."""

from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage
from PySide6.QtWidgets import QInputDialog

from lodandsy.application.card_editor_binding import CardEditorBinding
from lodandsy.application.card_media_controller import CardMediaController
from lodandsy.application.game_sheet_binding import GameSheetBinding
from lodandsy.application.rich_html import internal_entity_id
from lodandsy.domain.actor_state import ActorRef
from lodandsy.domain.card import EMPTY_DOCUMENT
from lodandsy.ui.card_document_state import CardDocumentState
from lodandsy.ui.card_editor import CardEditorWidget
from lodandsy.ui.game_labels import ATTRIBUTES_PAGE, MODIFIERS_PAGE, system_pages
from lodandsy.ui.window_manager import WorkspaceWindow
from lodandsy.ui.workspace_placement import WorkspacePlacement


class CardsController(QObject):
    pending_changed = Signal()

    def request_card_creation(self, parent):
        from lodandsy.ui.card_creation_dialog import CardCreationDialog

        return CardCreationDialog.get_card(parent)

    def __init__(
        self,
        window,
        windows,
        service,
        resources,
        media,
        table_factory,
        link_table,
        open_entity,
        copy_link,
        ensure_project,
    ):
        super().__init__(window)
        self.window, self.window_manager, self.service = window, windows, service
        self.resources, self.media = resources, media
        self.table_factory, self.link_table, self.open_entity, self.copy_card_link = (
            table_factory,
            link_table,
            open_entity,
            copy_link,
        )
        self.editors = {}
        self.bindings = {}
        self.game_bindings = {}
        self.documents = {}
        self.preferences = {}
        self._table_cards = {}
        self.placements_query = lambda reference: ()
        self.locate_placement = lambda map_id, token_id: None
        self.delete_actor = lambda reference, **kwargs: None
        self.reference_queries = None
        self.images = CardMediaController(window, service, media, resources, ensure_project)
        service.card_changed.connect(self._on_card_changed)
        service.actor_changed.connect(
            lambda key, actor, fields: self.refresh_relations(key, update_placements=False)
        )
        service.cards_deleted.connect(self._on_cards_deleted)
        service.cards_replaced.connect(self.reset)
        service.core.entity_changed.connect(self._link_entity_changed)
        service.core.entities_deleted.connect(self._link_entities_deleted)

    @property
    def cards(self):
        return self.service.cards

    @property
    def opened_ids(self):
        return tuple(self.editors)

    @property
    def project_root(self):
        return self.resources.root

    @staticmethod
    def card_editor_window_key(key):
        return f"card-editor:{key}"

    def edit_portrait(self, key):
        self.images.portrait(self.open_card_editor(key).widget())

    def reset(self):
        for key in tuple(self.editors):
            self.window_manager.close_window(self.card_editor_window_key(key))
        for state in self.documents.values():
            state.delete()
        self.documents.clear()
        self.preferences.clear()
        self._table_cards.clear()

    def capture_ui(self):
        result = {
            key: value
            for key, value in self.preferences.items()
            if any(c.id == key for c in self.cards.all())
        }
        for key, editor in self.editors.items():
            self.documents[key].capture(editor)
        for key, state in self.documents.items():
            result[key] = state.ui_values()
        return result

    @property
    def pending_count(self):
        return sum(editor.pending_input for editor in self.editors.values())

    def flush_edits(self):
        for editor in tuple(self.editors.values()):
            editor.flush_pending()
        self.service.field_edits.flush()

    def restore_ui(self, values):
        ids = {card.id for card in self.cards.all()}
        self.preferences = {
            key: value for key, value in values.items() if key in ids and isinstance(value, dict)
        }
        for key, editor in self.editors.items():
            if key in self.preferences:
                state = self.documents[key]
                state.load_ui_values(self.preferences[key])
                state.restore(editor)

    def _link_entity_changed(self, key, fields):
        if "parent_id" in fields:
            self._link_entities_deleted((key,))

    def _link_entities_deleted(self, keys):
        affected = (
            set().union(*(self._table_cards.get(key, set()) for key in keys)) if keys else set()
        )
        for key in affected:
            editor = self.editors.get(key)
            if editor:
                editor.refresh_table_links(keys)

    def _index_links(self, key):
        for target, ids in tuple(self._table_cards.items()):
            ids.discard(key)
            if not ids:
                self._table_cards.pop(target)
        try:
            card = self.cards.get(key)
        except ValueError:
            return
        for section in card.sections:
            if section.kind == "table_ref" and section.table_id:
                self._table_cards.setdefault(section.table_id, set()).add(key)

    def set_project_root(self, root):
        for state in self.documents.values():
            for document in state.documents():
                document.configure_resources(root, self.media.preview, self.media.image_size)
        for editor in self.editors.values():
            editor.refresh_links()

    def follow_link(self, url: QUrl, editor):
        text = url.toString()
        try:
            parsed = urlsplit(text)
            if parsed.scheme.lower() == "lodandsy":
                entity_id = internal_entity_id(text)
                try:
                    entity = self.service.entities.get(entity_id)
                except ValueError:
                    raise ValueError(
                        "Разорванная ссылка: документ удалён или отсутствует"
                    ) from None
                self.open_entity(entity.kind, entity.id)
            elif parsed.scheme.lower() in {"http", "https"} and parsed.hostname and url.isValid():
                if not QDesktopServices.openUrl(url):
                    raise ValueError("Не удалось открыть ссылку в системном браузере")
            elif not parsed.scheme and not parsed.path and parsed.fragment:
                editor.text_edit.scrollToAnchor(parsed.fragment)
            else:
                raise ValueError("Эта URI-схема заблокирована")
            editor.show_link_error("")
        except ValueError as error:
            editor.show_link_error(str(error))

    def _refresh_editor_links(self, editor):
        errors, targets = [], set()
        block = editor.text_edit.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().isAnchor():
                    href = fragment.charFormat().anchorHref()
                    if QUrl(href).scheme().lower() == "lodandsy":
                        try:
                            target = internal_entity_id(href)
                            targets.add(target)
                            self.service.entities.get(target)
                        except ValueError:
                            errors.append("Разорванная или неподдерживаемая ссылка на документ")
                iterator += 1
            block = block.next()
        editor.show_link_error(errors[0] if errors else "")
        editor._internal_targets = targets

    def _on_cards_deleted(self, card_ids: tuple[str, ...]) -> None:
        for card_id in card_ids:
            self._index_links(card_id)
            self.preferences.pop(card_id, None)
            self.window_manager.close_window(self.card_editor_window_key(card_id))
            state = self.documents.pop(card_id, None)
            if state is not None:
                state.delete()
        for editor in self.editors.values():
            if getattr(editor, "_internal_targets", set()).intersection(card_ids):
                editor.refresh_links()

    def _on_card_changed(self, card_id: str, fields: frozenset[str]) -> None:
        self.refresh_relations(card_id)
        if card_id not in self.editors:
            state = self.documents.get(card_id)
            if state is not None:
                card = self.cards.get(card_id)
                state.prune(
                    {section.id for section in card.sections}
                    | dict(system_pages(card.card_type)).keys()
                )
                for section in card.sections:
                    target = state.existing(section.id)
                    if target and (card_id, section.id) not in self.service.field_drafts:
                        target.sync_content(section.content or EMPTY_DOCUMENT)
        dock = self.window_manager.find_window(self.card_editor_window_key(card_id))
        if dock is not None and "title" in fields:
            dock.setWindowTitle(self.cards.get(card_id).title)
        self._index_links(card_id)

    def open_card_editor(
        self,
        card_id: str,
    ) -> WorkspaceWindow:
        card = self.cards.get(card_id)
        self.service.select_card(card_id)
        key = self.card_editor_window_key(card_id)
        existing = self.window_manager.find_window(key)
        if existing is not None:
            self.window_manager.focus_window(key)
            if self.editors[card_id].body.currentIndex() == 0:
                self.editors[card_id].text_edit.setFocus()
            return existing
        try:
            dock = self.window_manager.open_window(
                key=key,
                title=card.title,
                content_factory=lambda: self._create_card_editor(card_id),
                placement=WorkspacePlacement.CENTER,
            )
        except Exception:
            self._dispose_card_editor(card_id)
            raise
        dock.closed.connect(lambda closed: self._on_card_editor_closed(card_id, closed))
        self.documents[card_id].restore(self.editors[card_id])
        if self.editors[card_id].body.currentIndex() == 0:
            self.editors[card_id].text_edit.setFocus()
        return dock

    def open_game_sheet(self, card_id, actor_id=None):
        dock = self.open_card_editor(card_id)
        editor = self.editors[card_id]
        if card_id in self.game_bindings:
            self.game_bindings[card_id].select_actor(actor_id)
            editor.select_section(ATTRIBUTES_PAGE)
        elif self.cards.get(card_id).card_type == "item":
            editor.select_section(MODIFIERS_PAGE)
        return dock

    def show_actor_sheet(self, reference):
        return self.open_game_sheet(reference.card_id, reference.actor_id)

    def _create_card_editor(self, card_id):
        state = self.documents.get(card_id)
        if state is None:
            state = CardDocumentState(
                self.cards.get(card_id).content, self.window, self.cards.get(card_id).description_id
            )
            values = self.preferences.get(card_id)
            if values is not None:
                state.load_ui_values(values)
            self.documents[card_id] = state
        editor = CardEditorWidget()
        editor.relations.actor_requested.connect(
            lambda actor_id: self.show_actor_sheet(ActorRef(card_id, actor_id))
        )
        editor.relations.placement_requested.connect(
            lambda map_id, token_id: self.locate_placement(map_id, token_id)
        )
        editor.relations.inventory_requested.connect(lambda key: self.open_entity("table", key))
        editor.relations.delete_requested.connect(lambda actor: self._delete_actor(card_id, actor))
        editor.pending_changed.connect(self.pending_changed)
        editor.document_state = state
        editor.table_factory = lambda section, previous=None: self.table_factory(
            section.table_id, card_id, previous
        )
        editor.section_action_requested.connect(
            lambda action, key, value: self._section_action(card_id, action, key, value)
        )

        def configure(document):
            document.configure_resources(
                self.project_root, self.media.preview, self.media.image_size
            )
            if not getattr(document, "images_connected", False):
                self.media.ready.connect(document.image_ready)
                document.images_connected = True

        editor.configure_document = configure
        if state.document is not None:
            configure(state.document)
        editor.portrait_panel.image_provider = lambda key: (
            self.media.cached_preview(self.project_root, self.resources.assets[key].path)
            if key in self.resources.assets
            else QImage()
        )
        self.media.ready.connect(editor.portrait_panel.refresh_image)
        editor.portrait_panel.image_requested.connect(lambda: self.images.portrait(editor))
        editor.entity_options = self.service.entities.summaries
        editor.reference_queries = self.reference_queries
        editor.image_requested.connect(lambda source: self.images.request(editor, source))
        editor.link_activated.connect(lambda url: self.follow_link(url, editor))
        editor.links_changed.connect(lambda: self._refresh_editor_links(editor))
        editor.copy_link_requested.connect(self.copy_card_link)
        if state.document is not None:
            editor.set_document(card_id, state.document)
        active_section = state.active_section
        binding = CardEditorBinding(self.service, editor, card_id)
        state.active_section = active_section
        self.editors[card_id] = editor
        self.bindings[card_id] = binding
        if self.cards.get(card_id).card_type in {"character", "creature", "object"}:
            self.game_bindings[card_id] = GameSheetBinding(
                self.service,
                editor.game_sheet,
                card_id,
                lambda key: self.open_entity("table", key),
                open_base_inventory=lambda: editor.select_section(
                    next(s.id for s in self.cards.get(card_id).sections if s.purpose == "inventory")
                ),
            )
        self._index_links(card_id)
        self.refresh_relations(card_id)
        return editor

    def refresh_relations(self, card_id, *, update_placements=True):
        editor = self.editors.get(card_id)
        if editor is None:
            return
        try:
            card = self.service.get_card(card_id)
            rows = []
            for actor in sorted(card.actors, key=lambda a: a.name):
                name, summary, inventory = self.service.participant_info(card_id, actor.id)
                rows.append(
                    (
                        actor.id,
                        name,
                        summary,
                        inventory,
                        self.placements_query(ActorRef(card_id, actor.id))
                        if update_placements or actor.id not in editor.relations.rows else None,
                    )
                )
            editor.relations.set_rows(tuple(rows))
        except ValueError:
            editor.relations.set_rows(())

    def _delete_actor(self, card_id, actor_id):
        from PySide6.QtWidgets import QMessageBox

        reference = ActorRef(card_id, actor_id)
        actor = self.service.get_actor(reference)
        count = len(self.placements_query(reference))
        if (
            QMessageBox.question(
                self.window,
                "Удалить участника?",
                f"{actor.name}\nРазмещений: {count}. "
                "Его индивидуальный инвентарь также будет удалён. "
                "Карточка и остальные участники сохранятся.",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.delete_actor(reference, confirmed=True)

    def _section_action(self, card_id, action, key, value):
        from PySide6.QtWidgets import QMessageBox

        session = self.service
        card = self.cards.get(card_id)
        editor = self.editors[card_id]
        editor.flush_pending()
        try:
            if action == "add_text":
                title, ok = QInputDialog.getText(editor, "Новая вкладка", "Название:")
                if ok and title.strip():
                    section = session.add_section(card_id, title)
                    editor.select_section(section.id)
            elif action in {"add_table", "table", "link_table"}:
                if action == "add_table":
                    title, ok = QInputDialog.getText(editor, "Табличная вкладка", "Название:")
                    if not ok or not title.strip():
                        return
                else:
                    title = card.section(key).title
                children = [
                    e
                    for e in session.entities.summaries()
                    if e.kind == "table" and e.parent_id == card_id
                ]
                labels = ["Создать новую таблицу", *[e.title + " · " + e.id[:8] for e in children]]
                choice, ok = QInputDialog.getItem(
                    editor, "Дочерняя таблица", "Таблица:", labels, 0, False
                )
                if not ok:
                    return
                existing = children[labels.index(choice) - 1].id if labels.index(choice) else None
                if action == "add_table":
                    key = session.add_section(card_id, title, kind="table_ref").id
                self.link_table(
                    card_id,
                    key,
                    existing_id=existing,
                    replace_link=action == "link_table",
                    title=title,
                )
                editor.select_section(key)
            elif action == "rename":
                title, ok = QInputDialog.getText(
                    editor, "Название вкладки", "Название:", text=card.section(key).title
                )
                if ok and title.strip():
                    session.update_section(card_id, key, title=title)
            elif action == "delete":
                if (
                    QMessageBox.question(
                        editor,
                        "Удалить вкладку",
                        "Удалить вкладку и её текст? Связанная таблица сохранится.",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    == QMessageBox.StandardButton.Yes
                ):
                    session.delete_section(card_id, key)
            elif action in {"left", "right"}:
                position = card.section(key).position + (1 if action == "right" else -1)
                if 0 <= position < len(card.sections):
                    session.move_section(card_id, key, position)
        except ValueError as error:
            editor.show_link_error(str(error))

    def _dispose_card_editor(self, card_id: str) -> None:
        game_binding = self.game_bindings.pop(card_id, None)
        if game_binding:
            game_binding.dispose()
        editor = self.editors.pop(card_id, None)
        if editor is not None:
            editor.flush_pending()
            self.documents[card_id].capture(editor)
        binding = self.bindings.pop(card_id, None)
        if binding is not None:
            binding.dispose()

    def _on_card_editor_closed(self, card_id: str, dock) -> None:
        if self.editors.get(card_id) is dock.widget():
            self._dispose_card_editor(card_id)
