"""A passive project catalogue. Only ProjectController may select a world."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


class ProjectChooser(QDialog):
    open_requested = Signal(str)
    locate_requested = Signal(str)
    remove_requested = Signal(str)
    create_requested = Signal()
    browse_requested = Signal()

    def __init__(self, entries, parent=None, *, welcome=False):
        super().__init__(parent)
        if welcome:
            self.setWindowFlags(
                Qt.WindowType.Window
                | Qt.WindowType.WindowTitleHint
                | Qt.WindowType.WindowSystemMenuHint
                | Qt.WindowType.WindowCloseButtonHint
            )
        self.setWindowTitle("LODANDSY" if welcome else "Открыть проект")
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        title = QLabel("Добро пожаловать в LODANDSY" if welcome else "Ваши проекты")
        title.setStyleSheet("font-size: 20px; font-weight: 600; padding: 8px 0;")
        layout.addWidget(title)
        self.projects = QListWidget()
        self.projects.setAccessibleName("Известные проекты")
        layout.addWidget(self.projects, 1)
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #f19a9a;")
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        self.open_button = QPushButton("Открыть")
        self.open_button.setDefault(True)
        self.open_button.clicked.connect(self.open_selected)
        actions.addWidget(self.open_button)
        create = QPushButton("Создать проект…")
        create.clicked.connect(self.create_requested)
        actions.addWidget(create)
        actions.addStretch()
        browse = QPushButton("Выбрать другую папку…")
        browse.clicked.connect(self.browse_requested)
        actions.addWidget(browse)
        layout.addLayout(actions)
        secondary = QHBoxLayout()
        locate = QPushButton("Указать новое расположение…")
        locate.clicked.connect(lambda: self._selected(self.locate_requested))
        secondary.addWidget(locate)
        remove = QPushButton("Убрать из списка")
        remove.setToolTip("Папка проекта и её содержимое останутся на диске")
        remove.clicked.connect(lambda: self._selected(self.remove_requested))
        secondary.addWidget(remove)
        secondary.addStretch()
        layout.addLayout(secondary)
        self.projects.itemDoubleClicked.connect(lambda _: self.open_selected())
        self.projects.currentItemChanged.connect(
            lambda item, _: self.open_button.setEnabled(item is not None)
        )
        self.set_entries(entries)

    def set_entries(self, entries):
        self.projects.clear()
        for entry in entries:
            item = QListWidgetItem(entry["title"] + "\n" + entry["path"])
            item.setData(Qt.ItemDataRole.UserRole, entry["path"])
            self.projects.addItem(item)
        self.projects.setCurrentRow(0)
        self.open_button.setEnabled(bool(entries))

    def _selected(self, signal):
        item = self.projects.currentItem()
        if item:
            signal.emit(item.data(Qt.ItemDataRole.UserRole))

    def open_selected(self):
        self._selected(self.open_requested)
