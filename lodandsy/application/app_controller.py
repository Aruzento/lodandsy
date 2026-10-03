from lodandsy.application.application_session import (
    ApplicationSession,
)
from lodandsy.application.card_editor_binding import (
    CardEditorBinding,
)
from lodandsy.application.card_inspector_binding import (
    CardInspectorBinding,
)
from lodandsy.domain.card import Card
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.card_editor import CardEditorWidget
from lodandsy.ui.window_manager import WindowManager
from lodandsy.ui.workspace_dock import WorkspaceDock
from lodandsy.ui.workspace_placement import (
    WorkspacePlacement,
)


class AppController:
    CARD_EDITOR_WINDOW_KEY = "card-editor"

    def __init__(
        self,
        window: AppShell,
        cards: CardCollection | None = None,
    ) -> None:
        self.window = window

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

        self.card_editor_widget: (
            CardEditorWidget | None
        ) = None

        self.card_editor_binding: (
            CardEditorBinding | None
        ) = None

        self.inspector_binding = CardInspectorBinding(
            session=self.session,
            inspector=self.window.inspector_panel,
            on_cards_changed=self.refresh_tree,
        )

        self.window.tree_panel.card_selected.connect(
            self.session.select_card
        )

        self.window.tree_panel.card_open_requested.connect(
            self.open_card_editor
        )

        self.window.tree_panel.create_requested.connect(
            self._on_create_requested
        )

        self.window.tree_panel.rename_requested.connect(
            self.rename_card
        )

        self.window.tree_panel.delete_requested.connect(
            self.delete_card
        )

        self.window.tree_panel.reparent_requested.connect(
            self._on_reparent_requested
        )

        self.refresh_tree()

    def refresh_tree(self) -> None:
        self.window.tree_panel.set_cards(
            self.cards.all()
        )

    def open_card_editor(
        self,
        card_id: str,
    ) -> WorkspaceDock:
        # select_card одновременно валидирует,
        # что такая Card существует.
        self.session.select_card(
            card_id
        )

        was_open = (
            self.window_manager.find_window(
                self.CARD_EDITOR_WINDOW_KEY
            )
            is not None
        )

        try:
            dock = self.window_manager.open_window(
                key=self.CARD_EDITOR_WINDOW_KEY,
                title="Card Editor",
                content_factory=self._create_card_editor,
                placement=WorkspacePlacement.CENTER,
            )
        except Exception:
            if not was_open:
                self._dispose_card_editor()

            raise

        if not was_open:
            dock.closed.connect(
                self._on_card_editor_closed
            )

        return dock

    def create_card(
        self,
        title: str,
        parent_id: str | None = None,
    ) -> Card:
        card = self.cards.create(
            title,
            parent_id=parent_id,
        )

        self.refresh_tree()
        self.inspector_binding.refresh()

        return card

    def rename_card(
        self,
        card_id: str,
        title: str,
    ) -> None:
        self.cards.rename(
            card_id,
            title,
        )

        self.refresh_tree()
        self.inspector_binding.refresh()

    def reparent_card(
        self,
        card_id: str,
        parent_id: str | None,
    ) -> None:
        self.cards.reparent(
            card_id,
            parent_id,
        )

        self.refresh_tree()
        self.inspector_binding.refresh()

    def delete_card(
        self,
        card_id: str,
    ) -> None:
        deleted_ids = self.cards.delete(
            card_id
        )

        if (
            self.session.current_card_id
            in deleted_ids
        ):
            self.session.clear_selection()

        self.refresh_tree()
        self.inspector_binding.refresh()

    def _create_card_editor(
        self,
    ) -> CardEditorWidget:
        if (
            self.card_editor_widget is not None
            or self.card_editor_binding is not None
        ):
            raise RuntimeError(
                "Card Editor already exists"
            )

        editor = CardEditorWidget()

        binding = CardEditorBinding(
            session=self.session,
            editor=editor,
        )

        self.card_editor_widget = editor
        self.card_editor_binding = binding

        return editor

    def _on_card_editor_closed(
        self,
        dock: object,
    ) -> None:
        if not isinstance(
            dock,
            WorkspaceDock,
        ):
            return

        if (
            dock.key
            != self.CARD_EDITOR_WINDOW_KEY
        ):
            return

        self._dispose_card_editor()

    def _dispose_card_editor(self) -> None:
        binding = self.card_editor_binding

        if binding is not None:
            binding.dispose()

        self.card_editor_binding = None
        self.card_editor_widget = None

    def _on_create_requested(
        self,
        title: str,
        parent_id: object,
    ) -> None:
        resolved_parent_id = (
            self._optional_card_id(
                parent_id
            )
        )

        self.create_card(
            title,
            resolved_parent_id,
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