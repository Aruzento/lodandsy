from lodandsy.application.application_session import ApplicationSession
from lodandsy.ui.card_editor import CardEditorWidget


class CardEditorBinding:
    def __init__(
        self,
        session: ApplicationSession,
        editor: CardEditorWidget,
    ) -> None:
        self.session = session
        self.editor = editor

        self.editor.content_changed.connect(
            self._on_content_changed
        )

        self.session.current_card_changed.connect(
            self._on_current_card_changed
        )

        self.refresh()

    def refresh(self) -> None:
        card = self.session.current_card

        if card is None:
            self.editor.clear_card()
            return

        self.editor.set_card(
            card.id,
            card.content,
        )

    def _on_current_card_changed(
        self,
        _card_id: object,
    ) -> None:
        self.refresh()

    def _on_content_changed(
        self,
        card_id: str,
        content: str,
    ) -> None:
        if card_id != self.session.current_card_id:
            return

        self.session.cards.update_content(
            card_id,
            content,
        )