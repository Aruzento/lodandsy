from lodandsy.application.application_session import (
    ApplicationSession,
)
from lodandsy.ui.card_editor import CardEditorWidget


class CardEditorBinding:
    def __init__(
        self,
        session: ApplicationSession,
        editor: CardEditorWidget,
        card_id: str,
    ) -> None:
        self.session = session
        self.editor = editor
        self.card_id = card_id
        self.session.cards.get(card_id)

        self._disposed = False

        self.editor.content_changed.connect(
            self._on_content_changed
        )

        self.session.card_changed.connect(self._on_card_changed)
        self.session.cards_deleted.connect(self._on_cards_deleted)

        self.refresh()

    @property
    def is_disposed(self) -> bool:
        return self._disposed

    def refresh(self) -> None:
        if self._disposed:
            return

        card = self.session.cards.get(self.card_id)

        self.editor.set_card(
            card.id,
            card.content,
        )

    def dispose(self) -> None:
        if self._disposed:
            return

        self._disposed = True

        self.editor.content_changed.disconnect(
            self._on_content_changed
        )

        self.session.card_changed.disconnect(self._on_card_changed)
        self.session.cards_deleted.disconnect(self._on_cards_deleted)

    def _on_cards_deleted(self, card_ids: tuple[str, ...]) -> None:
        if self.card_id in card_ids:
            self.editor.clear_card()
            self.dispose()

    def _on_card_changed(self, card_id: str, fields: frozenset[str]) -> None:
        if card_id == self.editor.card_id and "content" in fields:
            self.refresh()

    def _on_content_changed(
        self,
        card_id: str,
        content: str,
    ) -> None:
        if self._disposed:
            return

        if card_id != self.card_id:
            return

        self.session.update_card(card_id, content=content)
