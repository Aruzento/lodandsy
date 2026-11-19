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
        self.editor.portrait_panel.changed.connect(self._on_portrait_changed)
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
        self.editor.portrait_panel.set_portrait(card.portrait)

    def dispose(self) -> None:
        if self._disposed:
            return

        self._disposed = True

        self.editor.content_changed.disconnect(
            self._on_content_changed
        )

        self.session.card_changed.disconnect(self._on_card_changed)
        self.session.cards_deleted.disconnect(self._on_cards_deleted)
        self.editor.portrait_panel.changed.disconnect(self._on_portrait_changed)

    def _on_cards_deleted(self, card_ids: tuple[str, ...]) -> None:
        if self.card_id in card_ids:
            self.editor.clear_card()
            self.dispose()

    def _on_card_changed(self, card_id: str, fields: frozenset[str]) -> None:
        if card_id == self.editor.card_id and fields & {"content", "portrait"}:
            self.refresh()

    def _on_portrait_changed(self, portrait):
        if not self._disposed:
            self.session.update_card(self.card_id, portrait=portrait)

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
