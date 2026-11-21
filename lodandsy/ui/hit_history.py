"""Native, explicit per-level input; text transport is private to shared FieldEdits."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class HitHistoryEdit(QWidget):
    edit_started = Signal()
    buffer_changed = Signal(str)
    commit_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self):
        super().__init__()
        self.raw = ""
        self.level, self.die = 1, None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel("История не задана")
        self.summary.setWordWrap(True)
        self.button = QPushButton("По уровням…")
        self.button.clicked.connect(self.open_editor)
        layout.addWidget(self.summary, 1)
        layout.addWidget(self.button)

    def set_value(self, text, *, force=False):
        self.raw = text
        count = len(text.split(",")) if text.strip() else 0
        self.summary.setText(f"Уровней: {count} из {self.level}" if count else "История не задана")

    def open_editor(self):
        self.edit_started.emit()
        dialog = QDialog(self)
        dialog.setWindowTitle("Прирост хитов по уровням")
        dialog.resize(400, 480)
        layout = QVBoxLayout(dialog)
        notice = QLabel(
            "Первый уровень — полная кость класса. Далее — сохранённый прирост без Телосложения."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        values = self.raw.split(",") if self.raw.strip() else []
        controls = []
        for index in range(max(1, min(100, self.level))):
            edit = QLineEdit(values[index].strip() if index < len(values) else "")
            edit.setPlaceholderText("Не задано")
            edit.setAccessibleName(f"Уровень {index + 1}: прирост хитов")
            form.addRow(f"Уровень {index + 1}", edit)
            controls.append(edit)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        error = QLabel()
        error.setWordWrap(True)
        error.setObjectName("errorNotice")
        layout.addWidget(error)
        buttons = QDialogButtonBox()
        buttons.addButton("Сохранить историю", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("Отмена", QDialogButtonBox.ButtonRole.RejectRole)

        def accept():
            raw = [control.text().strip() for control in controls]
            if any(raw):
                try:
                    parsed = [int(value) for value in raw]
                    if any(not 1 <= value <= (self.die or 100) for value in parsed):
                        raise ValueError()
                except ValueError:
                    error.setText(
                        "Заполните каждый уровень целым приростом от 1 до кости класса "
                        "или очистите всю историю."
                    )
                    return
            dialog.accept()

        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.raw = (
                ", ".join(c.text().strip() for c in controls)
                if any(c.text().strip() for c in controls)
                else ""
            )
            self.buffer_changed.emit(self.raw)
            self.commit_requested.emit(self.raw)
        else:
            self.cancel_requested.emit()
