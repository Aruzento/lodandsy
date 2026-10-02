from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


class CardEditorWidget(QWidget):
    content_changed = Signal(str, str)

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.setObjectName("cardEditor")

        self._card_id: str | None = None

        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setObjectName("cardContentEditor")
        self.text_edit.setPlaceholderText(
            "Write Markdown..."
        )
        self.text_edit.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.text_edit)

        self.text_edit.textChanged.connect(
            self._on_text_changed
        )

    @property
    def card_id(self) -> str | None:
        return self._card_id

    def set_card(
        self,
        card_id: str,
        content: str,
    ) -> None:
        self._card_id = card_id

        blocker = QSignalBlocker(self.text_edit)

        self.text_edit.setPlainText(content)
        self.text_edit.setEnabled(True)

        del blocker

    def clear_card(self) -> None:
        self._card_id = None

        blocker = QSignalBlocker(self.text_edit)

        self.text_edit.clear()
        self.text_edit.setEnabled(False)

        del blocker

    def _on_text_changed(self) -> None:
        if self._card_id is None:
            return

        self.content_changed.emit(
            self._card_id,
            self.text_edit.toPlainText(),
        )