"""Name and destination preview for creating or restoring a world."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from lodandsy.ui.theme import SPACE_LG, SPACE_SM, apply_role


class ProjectNameDialog(QDialog):
    def __init__(self, destination, submit, parent, *, restoring=False, suggestion=""):
        super().__init__(parent)
        self._destination, self._submit = destination, submit
        self.setWindowTitle("Восстановить проект" if restoring else "Создать проект")
        self.resize(530, 200)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_SM)
        label = QLabel("Название проекта")
        self.name = QLineEdit(suggestion)
        self.name.setPlaceholderText("Например, Этар")
        self.name.setAccessibleName(label.text())
        label.setBuddy(self.name)
        layout.addWidget(label)
        layout.addWidget(self.name)

        self.path = QLabel()
        self.path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path.setTextFormat(Qt.TextFormat.PlainText)
        self.path.setWordWrap(True)
        self.path.setAccessibleName("Путь нового проекта")
        apply_role(self.path, "empty")
        layout.addWidget(self.path)
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        apply_role(self.error, "error")
        layout.addWidget(self.error)
        layout.addStretch()

        actions = QHBoxLayout()
        actions.addStretch()
        self.confirm = QPushButton("Восстановить проект" if restoring else "Создать проект")
        self.confirm.setDefault(True)
        apply_role(self.confirm, "primary")
        self.confirm.clicked.connect(self._accept_name)
        actions.addWidget(self.confirm)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        layout.addLayout(actions)
        self.name.textChanged.connect(self._preview)
        self._preview(self.name.text())
        self.name.setFocus()
        self.name.selectAll()

    def _show_error(self, error):
        self.error.setText(error)
        self.error.setVisible(bool(error))

    def _preview(self, name):
        try:
            path = self._destination(name) if name else None
        except (OSError, ValueError) as error:
            self._show_error(str(error))
            self.path.clear()
            self.confirm.setEnabled(False)
            return
        self.path.setText(str(path) if path else "Путь появится после ввода названия.")
        self.confirm.setEnabled(path is not None)
        self._show_error("")

    def _accept_name(self):
        try:
            if self._submit(self.name.text()):
                self.accept()
        except (OSError, ValueError) as error:
            self._show_error(str(error))
