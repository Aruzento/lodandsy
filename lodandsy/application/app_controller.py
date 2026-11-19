from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QKeySequence, QTextCursor
from PySide6.QtWidgets import QInputDialog

from lodandsy.application.application_session import (
    ApplicationSession,
)
from lodandsy.application.card_editor_binding import (
    CardEditorBinding,
)
from lodandsy.application.card_images import CardImages
from lodandsy.application.card_inspector_binding import (
    CardInspectorBinding,
)
from lodandsy.application.clipboard import clipboard_writer, copy_text
from lodandsy.application.markdown_links import card_link, internal_card_id
from lodandsy.application.module_controller import ModuleController
from lodandsy.domain.card import Card
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.card_document_state import CardDocumentState
from lodandsy.ui.card_editor import CardEditorWidget
from lodandsy.ui.card_search_dialog import CardSearchDialog
from lodandsy.ui.window_manager import WindowManager, WorkspaceWindow
from lodandsy.ui.workspace_placement import (
    WorkspacePlacement,
)


class AppController:
    @staticmethod
    def card_editor_window_key(card_id: str) -> str:
        return f"card-editor:{card_id}"

    def __init__(
        self,
        window: AppShell,
        cards: CardCollection | None = None,
    ) -> None:
        self.window = window
        clipboard_writer().message.connect(window.show_notice)
        self.project_root: Path | None = None
        self.navigator_selection: str | None = None

        self.cards = (
            cards
            if cards is not None
            else CardCollection()
        )

        self.session = ApplicationSession(
            cards=self.cards,
            parent=self.window,
        )

        self.window_manager = WindowManager(
            self.window
        )

        self.card_editors: dict[str, CardEditorWidget] = {}
        self.card_editor_bindings: dict[str, CardEditorBinding] = {}
        self.card_document_states: dict[str, CardDocumentState] = {}
        self.saved_card_preferences: dict[str, dict] = {}
        self.card_images = CardImages(self)

        self.inspector_binding = CardInspectorBinding(
            session=self.session,
            inspector=self.window.inspector_panel,
        )

        self.window.tree_panel.entity_selected.connect(
            self._on_navigator_selected
        )

        self.window.tree_panel.entity_open_requested.connect(
            self.open_entity
        )

        self.window.tree_panel.create_requested.connect(
            self._on_create_requested
        )
        self.window.tree_panel.template_create_requested.connect(self._on_create_requested)

        self.window.tree_panel.rename_requested.connect(
            self.rename_card
        )

        self.window.tree_panel.delete_requested.connect(
            self.delete_card
        )

        self.window.tree_panel.reparent_requested.connect(
            self._on_reparent_requested
        )
        self.window.tree_panel.move_requested.connect(self._on_move_requested)
        self.window.tree_panel.copy_link_requested.connect(self.copy_card_link)
        self.window.tree_panel.move_parent_requested.connect(self.request_move_card)

        self.session.card_created.connect(self._on_structure_changed)
        self.session.cards_deleted.connect(self._on_cards_deleted)
        self.session.card_changed.connect(self._on_card_changed)
        self.session.cards_replaced.connect(self.refresh_tree)
        self.session.current_card_changed.connect(self._on_selected_card_changed)
        self._search_dialog: CardSearchDialog | None = None
        search_action = QAction("Найти карточку…", self.window)
        search_action.setShortcut(QKeySequence.StandardKey.Find)
        search_action.triggered.connect(self.open_search)
        self.window.addAction(search_action)
        self.window.tree_panel.search_requested.connect(self.open_search)
        self.refresh_tree()
        self.modules = ModuleController(self)
        self.window.tree_panel.module_create_requested.connect(self.modules.request_create)
        self.window.tree_panel.module_rename_requested.connect(self.modules.request_rename)
        self.window.tree_panel.module_delete_requested.connect(self.modules.request_delete)
        self.modules.busy_changed.connect(lambda: self.window.tree_panel.set_map_creation_enabled(
            not self.modules.importing))
        for signal in [self.modules.session.map_changed, self.modules.session.table_changed,
                       self.modules.session.map_deleted, self.modules.session.table_deleted,
                       self.modules.session.replaced]:
            signal.connect(self._refresh_navigator_modules)

    def open_entity(self, kind, entity_id):
        keys = {"card": "card-editor:", "map": "map:", "table": "table:"}
        if kind == "dice":
            return self.open_document("dice")
        if kind not in keys:
            raise ValueError("Неподдерживаемый объект навигации")
        return self.open_document(keys[kind] + entity_id)

    def request_move_card(self, card_id):
        card = self.cards.get(card_id)
        excluded = {card_id, *self.cards.descendant_ids(card_id)}
        choices = [(None, "Корень карточек"), *((item.id, f"{item.title} · {item.id}")
                    for item in self.cards.all() if item.id not in excluded)]
        labels = [label for _key, label in choices]
        selected = next((i for i, (key, _label) in enumerate(choices) if key == card.parent_id), 0)
        label, accepted = QInputDialog.getItem(self.window, "Переместить карточку", "Родитель:",
                                              labels, selected, False)
        if accepted:
            self.reparent_card(card_id, choices[labels.index(label)][0])

    def _on_navigator_selected(self, kind, entity_id):
        self.navigator_selection = f"{kind}:{entity_id}"
        if kind == "card":
            self.session.select_card(entity_id)
        else:
            self.session.clear_selection()
            self._update_navigator_summary()

    def _on_selected_card_changed(self, card_id):
        if card_id is not None:
            self.navigator_selection = f"card:{card_id}"
            self.window.tree_panel.select_card(card_id)
        elif self.navigator_selection and self.navigator_selection.startswith("card:"):
            self.navigator_selection = None
            self.window.tree_panel.select_node(None)

    def _update_navigator_summary(self):
        if not self.navigator_selection:
            if self.session.current_card_id is None:
                self.window.inspector_panel.clear_card()
            return
        kind, entity_id = self.navigator_selection.split(":", 1)
        if kind in {"map", "table"}:
            try:
                item = (self.modules.session.get_map(entity_id) if kind == "map"
                        else self.modules.session.get_table(entity_id))
                self.window.inspector_panel.show_entity_summary(item.id, item.title)
            except ValueError:
                self.window.inspector_panel.clear_card()
        elif kind != "card":
            self.window.inspector_panel.clear_card()

    def _refresh_navigator_modules(self, *_args):
        session = self.modules.session
        self.window.tree_panel.set_modules(
            tuple((item.id, item.title) for item in session.maps.values()),
            tuple((item.id, item.title) for item in session.tables.values()))
        key = self.window.tree_panel.current_node_key()
        if self.navigator_selection != key:
            self.navigator_selection = key
        self._update_navigator_summary()

    def open_search(self):
        if self._search_dialog is None:
            self._search_dialog = CardSearchDialog(self.session, self.window)
            self._search_dialog.card_open_requested.connect(self.open_card_editor)
        self._search_dialog.show()
        self._search_dialog.raise_()
        self._search_dialog.activateWindow()
        self._search_dialog.query.setFocus()

    def open_document(self, key: str):
        prefix = "card-editor:"
        if key.startswith(prefix):
            return self.open_card_editor(key[len(prefix):])
        if key.startswith("map:"):
            return self.modules.open_map(key[4:])
        if key.startswith("table:"):
            return self.modules.open_table(key[6:])
        if key == "dice":
            return self.modules.open_dice()
        raise ValueError("Неподдерживаемый документ")

    def copy_card_link(self, card_id: str):
        card = self.cards.get(card_id)
        copy_text(card_link(card.id, card.title))

    def set_project_root(self, root: Path | None):
        self.project_root = root
        for editor in self.card_editors.values():
            editor.preview.project_root = root
            editor.render_preview()

    def follow_link(self, url: QUrl, editor: CardEditorWidget):
        text = url.toString()
        try:
            parsed = urlsplit(text)
            if parsed.scheme.lower() == "lodandsy":
                card_id = internal_card_id(text)
                try:
                    self.cards.get(card_id)
                except ValueError:
                    raise ValueError(
                        "Разорванная ссылка: карточка удалена или отсутствует"
                    ) from None
                self.open_card_editor(card_id)
            elif parsed.scheme.lower() in {"http", "https"} and parsed.hostname and url.isValid():
                if not QDesktopServices.openUrl(url):
                    raise ValueError("Не удалось открыть ссылку в системном браузере")
            elif not parsed.scheme and not parsed.path and parsed.fragment:
                editor.preview.scrollToAnchor(parsed.fragment)
            else:
                raise ValueError("Эта URI-схема заблокирована")
            editor.show_link_error("")
        except ValueError as error:
            editor.show_link_error(str(error))

    def _refresh_preview_links(self, editor: CardEditorWidget):
        errors = []
        targets = set()
        document = editor.preview.document()
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().isAnchor():
                    href = fragment.charFormat().anchorHref()
                    if QUrl(href).scheme().lower() == "lodandsy":
                        try:
                            target_id = internal_card_id(href)
                            targets.add(target_id)
                            self.cards.get(target_id)
                        except ValueError:
                            message = "Разорванная или неподдерживаемая ссылка на карточку"
                            errors.append(message)
                            cursor = QTextCursor(document)
                            cursor.setPosition(fragment.position())
                            cursor.setPosition(fragment.position() + fragment.length(),
                                               QTextCursor.MoveMode.KeepAnchor)
                            format = fragment.charFormat()
                            format.setForeground(QColor("#db7777"))
                            format.setToolTip(message)
                            cursor.setCharFormat(format)
                iterator += 1
            block = block.next()
        editor.show_link_error(errors[0] if errors else "")
        editor._internal_targets = targets

    def _on_structure_changed(self, _ids: object) -> None:
        self.refresh_tree()

    def _on_cards_deleted(self, card_ids: tuple[str, ...]) -> None:
        for card_id in card_ids:
            self.saved_card_preferences.pop(card_id, None)
            self.window_manager.close_window(self.card_editor_window_key(card_id))
            state = self.card_document_states.pop(card_id, None)
            if state is not None:
                state.document.deleteLater()
        self.refresh_tree()
        for editor in self.card_editors.values():
            if getattr(editor, "_internal_targets", set()).intersection(card_ids):
                editor.render_preview()

    def _on_card_changed(self, card_id: str, fields: frozenset[str]) -> None:
        if "content" in fields and card_id not in self.card_editors:
            state = self.card_document_states.get(card_id)
            if state is not None:
                state.sync_content(self.cards.get(card_id).content)
        dock = self.window_manager.find_window(self.card_editor_window_key(card_id))
        if dock is not None and "title" in fields:
            dock.setWindowTitle(self.cards.get(card_id).title)
        if fields & {"parent_id", "position"}:
            self.refresh_tree()
        elif "title" in fields:
            self.window.tree_panel.tree_model.set_title(card_id, self.cards.get(card_id).title)

    def refresh_tree(self) -> None:
        self.window.tree_panel.set_cards(
            self.cards.summaries()
        )

    def replace_cards(self, cards: CardCollection) -> None:
        for key in self.window_manager.window_keys():
            self.window_manager.close_window(key)
        for state in self.card_document_states.values():
            state.document.deleteLater()
        self.card_document_states.clear()
        self.saved_card_preferences.clear()
        self.cards = cards
        self.session.replace_cards(cards)

    def open_card_editor(
        self,
        card_id: str,
    ) -> WorkspaceWindow:
        card = self.cards.get(card_id)
        self.session.select_card(card_id)
        key = self.card_editor_window_key(card_id)
        existing = self.window_manager.find_window(key)
        if existing is not None:
            self.window_manager.focus_window(key)
            self.card_editors[card_id].text_edit.setFocus()
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
        self.card_document_states[card_id].restore(self.card_editors[card_id])
        self.card_editors[card_id].text_edit.setFocus()
        return dock

    def create_card(
        self,
        title: str,
        parent_id: str | None = None,
        *, template_id: str = "empty",
    ) -> Card:
        return self.session.create_card(title, parent_id, template_id=template_id)

    def rename_card(self, card_id: str, title: str) -> None:
        self.session.update_card(card_id, title=title)

    def reparent_card(self, card_id: str, parent_id: str | None) -> None:
        self.session.update_card(card_id, parent_id=parent_id)

    def delete_card(self, card_id: str) -> None:
        self.session.delete_card(card_id)

    def _create_card_editor(self, card_id: str) -> CardEditorWidget:
        state = self.card_document_states.get(card_id)
        if state is None:
            state = CardDocumentState(self.cards.get(card_id).content, self.window)
            values = self.saved_card_preferences.get(card_id)
            if values is not None:
                state.load_ui_values(values)
            self.card_document_states[card_id] = state
        editor = CardEditorWidget()
        editor.preview.project_root = self.project_root
        editor.preview.image_provider = self.card_images.preview
        self.card_images.ready.connect(editor.queue_preview)
        editor.image_requested.connect(lambda source: self.card_images.request(editor, source))
        editor.link_activated.connect(lambda url: self.follow_link(url, editor))
        editor.preview_rendered.connect(lambda: self._refresh_preview_links(editor))
        editor.copy_link_requested.connect(self.copy_card_link)
        editor.set_document(card_id, state.document)
        binding = CardEditorBinding(self.session, editor, card_id)
        self.card_editors[card_id] = editor
        self.card_editor_bindings[card_id] = binding
        return editor

    def _dispose_card_editor(self, card_id: str) -> None:
        editor = self.card_editors.pop(card_id, None)
        if editor is not None:
            self.card_document_states[card_id].capture(editor)
        binding = self.card_editor_bindings.pop(card_id, None)
        if binding is not None:
            binding.dispose()

    def _on_card_editor_closed(self, card_id: str, dock: WorkspaceWindow) -> None:
        if self.card_editors.get(card_id) is dock.widget():
            self._dispose_card_editor(card_id)

    def _on_create_requested(
        self,
        title: str,
        parent_id: object,
        template_id: str = "empty",
    ) -> None:
        resolved_parent_id = (
            self._optional_card_id(
                parent_id
            )
        )

        self.create_card(
            title,
            resolved_parent_id,
            template_id=template_id,
        )

    def _on_move_requested(self, card_id: str, parent_id: object, position: int) -> None:
        self.session.update_card(
            card_id, parent_id=self._optional_card_id(parent_id), position=position
        )

    def _on_reparent_requested(
        self,
        card_id: str,
        parent_id: object,
    ) -> None:
        resolved_parent_id = (
            self._optional_card_id(
                parent_id
            )
        )

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

        raise TypeError(
            "Card id must be str or None"
        )
