from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QVBoxLayout


class CardSearchDialog(QDialog):
    card_open_requested = Signal(str)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("Найти карточку")
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
        for signal in [session.card_created, session.card_changed, session.cards_deleted,
                       session.cards_replaced]:
            signal.connect(self._schedule)
        self.refresh()

    def _schedule(self, *_args):
        self._timer.start()

    def refresh(self):
        needle = self.query.text().strip().casefold()
        self.results.clear()
        for card in self.session.cards.all():
            if (needle and needle not in card.title.casefold()
                    and needle not in card.content.casefold()):
                continue
            self.results.addItem(card.title)
            item = self.results.item(self.results.count() - 1)
            item.setData(Qt.ItemDataRole.UserRole, card.id)
            item.setToolTip(card.content[:200])
        self.count.setText(f"Найдено: {self.results.count()}")

    def _open(self, item):
        card_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            self.session.cards.get(card_id)
        except ValueError:
            self.refresh()
            return
        self.card_open_requested.emit(card_id)
