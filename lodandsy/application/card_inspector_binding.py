from lodandsy.application.application_session import ApplicationSession
from lodandsy.ui.inspector_panel import InspectorPanel


class CardInspectorBinding:
    def __init__(
        self,
        session: ApplicationSession,
        inspector: InspectorPanel,
    ) -> None:
        self.session = session
        self.inspector = inspector

        self.inspector.title_changed.connect(
            self._on_title_changed
        )
        self.inspector.parent_changed.connect(
            self._on_parent_changed
        )

        self.session.current_card_changed.connect(
            self._on_current_card_changed
        )
        self.session.card_created.connect(self._on_structure_changed)
        self.session.cards_deleted.connect(self._on_structure_changed)
        self.session.card_changed.connect(self._on_card_changed)
        self.session.cards_replaced.connect(self.refresh)

        self.refresh()

    def refresh(self) -> None:
        card = self.session.current_card

        if card is None:
            self.inspector.clear_card()
            return

        self.inspector.set_card(
            card_id=card.id,
            title=card.title,
            parent_id=card.parent_id,
            parent_options=self._build_parent_options(
                card.id
            ),
        )

    def _on_current_card_changed(
        self,
        _card_id: object,
    ) -> None:
        self.refresh()

    def _on_title_changed(
        self,
        card_id: str,
        title: str,
    ) -> None:
        if card_id != self.session.current_card_id:
            return

        self.session.update_card(card_id, title=title)

    def _on_parent_changed(
        self,
        card_id: str,
        parent_id: object,
    ) -> None:
        if card_id != self.session.current_card_id:
            return

        resolved_parent_id = self._optional_card_id(
            parent_id
        )

        self.session.update_card(card_id, parent_id=resolved_parent_id)

    def _on_structure_changed(self, _ids: object) -> None:
        self.refresh()

    def _on_card_changed(self, card_id: str, fields: frozenset[str]) -> None:
        if fields & {"title", "parent_id"}:
            self.refresh()

    def _build_parent_options(
        self,
        card_id: str,
    ) -> list[tuple[str | None, str]]:
        blocked_ids = {
            card_id,
            *self.session.cards.descendant_ids(card_id),
        }

        options: list[tuple[str | None, str]] = [
            (None, "Root")
        ]

        for card in self.session.cards.all():
            if card.id in blocked_ids:
                continue

            options.append(
                (
                    card.id,
                    card.title,
                )
            )

        return options

    @staticmethod
    def _optional_card_id(
        value: object,
    ) -> str | None:
        if value is None:
            return None

        if isinstance(value, str):
            return value

        raise TypeError(
            "Card id must be str or None"
        )
