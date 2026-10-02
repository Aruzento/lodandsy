from collections.abc import Callable

from lodandsy.application.application_session import ApplicationSession
from lodandsy.ui.inspector_panel import InspectorPanel


class CardInspectorBinding:
    def __init__(
        self,
        session: ApplicationSession,
        inspector: InspectorPanel,
        on_cards_changed: Callable[[], None] | None = None,
    ) -> None:
        self.session = session
        self.inspector = inspector
        self.on_cards_changed = on_cards_changed

        self.inspector.title_changed.connect(
            self._on_title_changed
        )
        self.inspector.parent_changed.connect(
            self._on_parent_changed
        )

        self.session.current_card_changed.connect(
            self._on_current_card_changed
        )

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

        self.session.cards.rename(
            card_id,
            title,
        )

        self._notify_cards_changed()

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

        self.session.cards.reparent(
            card_id,
            resolved_parent_id,
        )

        self._notify_cards_changed()

    def _notify_cards_changed(self) -> None:
        if self.on_cards_changed is not None:
            self.on_cards_changed()

        self.refresh()

    def _build_parent_options(
        self,
        card_id: str,
    ) -> list[tuple[str | None, str]]:
        blocked_ids = {
            card_id,
            *self._descendant_ids(card_id),
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

    def _descendant_ids(
        self,
        card_id: str,
    ) -> set[str]:
        descendants: set[str] = set()
        pending = [card_id]

        while pending:
            current_id = pending.pop()

            for card in self.session.cards.all():
                if card.parent_id != current_id:
                    continue

                if card.id in descendants:
                    continue

                descendants.add(card.id)
                pending.append(card.id)

        return descendants

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