from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QVBoxLayout

from lodandsy.application.rich_html import html_text


class CardSearchDialog(QDialog):
    card_open_requested = Signal(str)
    entity_open_requested = Signal(str, str)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("Найти документ")
        self.resize(520, 420)
        self.query = QLineEdit(self)
        self.query.setPlaceholderText("Заголовок или содержимое…")
        self.results = QListWidget(self)
        self.count = QLabel(self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.query)
        layout.addWidget(self.results)
        layout.addWidget(self.count)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self.refresh)
        self.query.textChanged.connect(lambda _text: self._timer.start())
        self.results.itemActivated.connect(self._open)
        for signal in [
            session.card_created,
            session.card_changed,
            session.cards_deleted,
            session.cards_replaced,
            session.entity_changed,
            session.entities_replaced,
        ]:
            signal.connect(self._schedule)
        self.refresh()

    def _schedule(self, *_args):
        self._timer.start()

    def refresh(self):
        needle = self.query.text().strip().casefold()
        self.results.clear()
        for card in self.session.entities.summaries():
            payload = self.session.entities.payload(card.id)
            content = (
                getattr(payload, "content", "")
                or " ".join(
                    str(value)
                    for row in getattr(payload, "rows", ())
                    for _, value in row.cells
                    if value is not None
                )
                or " ".join(
                    p.name + " " + p.config.expression() for p in getattr(payload, "presets", ())
                )
            )
            if card.kind == "card":
                from lodandsy.domain.card_schema import field_definition

                values = [html_text(s.content or "") for s in payload.sections]
                for key, value in payload.values:
                    if value is not None:
                        values.append(
                            html_text(value)
                            if field_definition(key).data_type == "richtext"
                            else ", ".join(value)
                            if isinstance(value, tuple)
                            else str(value)
                        )
                content = " ".join(values)
            if needle and needle not in card.title.casefold() and needle not in content.casefold():
                continue
            self.results.addItem(card.title)
            item = self.results.item(self.results.count() - 1)
            item.setData(Qt.ItemDataRole.UserRole, card.id)
            item.setToolTip(content[:200])
        self.count.setText(f"Найдено: {self.results.count()}")

    def _open(self, item):
        card_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            entity = self.session.entities.get(card_id)
        except ValueError:
            self.refresh()
            return
        self.entity_open_requested.emit(entity.kind, card_id)
        if entity.kind == "card":
            self.card_open_requested.emit(card_id)
