"""A passive project catalogue. Only ProjectController may select a world."""

from PySide6.QtCore import QDateTime, QLocale, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from lodandsy import APP_VERSION
from lodandsy.ui.theme import apply_role


class ProjectChooser(QDialog):
    open_requested = Signal(str)
    create_requested = Signal()
    browse_requested = Signal()

    def __init__(self, entries, parent=None, *, welcome=False, root=""):
        super().__init__(parent)
        if welcome:
            self.setWindowFlags(
                Qt.WindowType.Window
                | Qt.WindowType.WindowTitleHint
                | Qt.WindowType.WindowSystemMenuHint
                | Qt.WindowType.WindowCloseButtonHint
            )
        self.setWindowTitle(f"LODANDSY {APP_VERSION}" if welcome else "Открыть проект")
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        title = QLabel("Добро пожаловать в LODANDSY" if welcome else "Ваши проекты")
        apply_role(title, "heading")
        layout.addWidget(title)
        directory = QLabel(str(root))
        directory.setTextFormat(Qt.TextFormat.PlainText)
        directory.setWordWrap(True)
        apply_role(directory, "empty")
        layout.addWidget(directory)
        self.projects = QListWidget()
        self.projects.setAccessibleName("Проекты в папке «Документы»")
        layout.addWidget(self.projects, 1)
        self.empty = QLabel("В каталоге пока нет проектов. Создайте новый мир.")
        self.empty.setWordWrap(True)
        apply_role(self.empty, "empty")
        layout.addWidget(self.empty, 1)
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        apply_role(self.error, "error")
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        self.open_button = QPushButton("Открыть")
        self.open_button.setDefault(True)
        apply_role(self.open_button, "primary")
        self.open_button.clicked.connect(self.open_selected)
        actions.addWidget(self.open_button)
        self.create = QPushButton("Создать проект…")
        self.create.clicked.connect(self.create_requested)
        actions.addWidget(self.create)
        actions.addStretch()
        browse = QPushButton("Открыть другую папку…")
        browse.clicked.connect(self.browse_requested)
        actions.addWidget(browse)
        layout.addLayout(actions)
        self.projects.itemDoubleClicked.connect(lambda _: self.open_selected())
        self.projects.currentItemChanged.connect(self._selection_changed)
        self.set_entries(entries)

    def set_entries(self, entries):
        self.projects.clear()
        for entry in entries:
            error = entry.get("error", "")
            opened = QDateTime.fromString(entry.get("opened_at") or "", Qt.DateFormat.ISODate)
            if entry.get("status") == "incompatible":
                detail = f"Несовместимая версия SQLite {entry['schema_version']}"
            elif error:
                detail = "Ошибка чтения метаданных"
            else:
                detail = "Целостность проверяется при открытии"
                if opened.isValid():
                    date = QLocale.system().toString(
                        opened.toLocalTime(), QLocale.FormatType.ShortFormat,
                    )
                    detail += f" · Открыт {date}"
            item = QListWidgetItem(entry["title"] + "\n" + detail)
            item.setToolTip(entry["path"] + ("\n" + error if error else ""))
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.projects.addItem(item)
        first_valid = next((i for i, entry in enumerate(entries) if not entry.get("error")), 0)
        self.projects.setCurrentRow(first_valid)
        for widget in (self.projects, self.open_button):
            widget.setVisible(bool(entries))
        self.empty.setVisible(not entries)
        have_valid = any(not entry.get("error") for entry in entries)
        apply_role(self.create, "secondary" if have_valid else "primary")
        self.create.setDefault(not have_valid)

    def _selection_changed(self, item, _previous):
        entry = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.error.setText(entry.get("error", "") if entry else "")
        self.open_button.setEnabled(entry is not None and not entry.get("error"))

    def open_selected(self):
        if self.open_button.isEnabled() and (item := self.projects.currentItem()):
            self.open_requested.emit(item.data(Qt.ItemDataRole.UserRole)["path"])
