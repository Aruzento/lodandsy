"""Native navigation and one action area for project settings pages."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lodandsy.ui.icons import icon
from lodandsy.ui.theme import SPACE_LG, SPACE_MD, SPACE_SM, apply_role

SECTIONS = {
    "rules": ("Игровая система", "Правила и расчёты D&D 5e 2014 для открытого мира."),
    "currency": ("Валюты", "Номиналы и точные курсы относительно базовой единицы."),
    "categories": ("Категории предметов", "Категории карточек Item для лута и магазина."),
    "backup": ("Резервное копирование", "Создаёт копию сохранённых данных и ресурсов мира."),
    "restore": ("Восстановление", "Восстанавливает мир из резервной копии в новую папку."),
}


class SettingsDialog(QDialog):
    def __init__(self, name, rules, economy, backup, restore, parent):
        super().__init__(parent)
        self.rules, self.economy = rules, economy
        self._actions = {"backup": backup, "restore": restore}
        self._force_close = False
        self.setWindowTitle(f"Настройки LODANDSY — {name}")
        self.setWindowIcon(icon("settings"))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumSize(584, 420)
        available = parent.screen().availableGeometry().size() - QSize(32, 64)
        self.resize(QSize(900, 610).boundedTo(available))

        outer = QHBoxLayout(self)
        outer.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_LG, SPACE_MD)
        outer.setSpacing(SPACE_LG)
        self.navigation = QTreeWidget()
        self.navigation.setObjectName("settingsNavigation")
        self.navigation.setAccessibleName("Разделы настроек")
        self.navigation.setHeaderHidden(True)
        self.navigation.setRootIsDecorated(False)
        self.navigation.setItemsExpandable(False)
        self.navigation.setIndentation(8)
        self.navigation.setFixedWidth(178)
        self._sections = {}
        for label, sections in (
            ("Проект", ("rules", "currency", "categories")),
            ("Данные", ("backup", "restore")),
        ):
            group = QTreeWidgetItem(self.navigation, [label])
            group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for section in sections:
                label = "Резервные копии" if section == "backup" else SECTIONS[section][0]
                item = QTreeWidgetItem(group, [label])
                item.setData(0, Qt.ItemDataRole.UserRole, section)
                item.setToolTip(0, SECTIONS[section][0])
                self._sections[section] = item
        self.navigation.expandAll()
        outer.addWidget(self.navigation)

        column = QVBoxLayout()
        column.setSpacing(SPACE_SM)
        title = QLabel()
        title.setWordWrap(True)
        self.title = title
        apply_role(title, "heading")
        self.description = QLabel()
        self.description.setWordWrap(True)
        apply_role(self.description, "empty")
        column.addWidget(title)
        column.addWidget(self.description)

        self.pages = QStackedWidget()
        self.pages.addWidget(rules)
        self.pages.addWidget(economy)
        self.data_page = QWidget()
        self.pages.addWidget(self.data_page)
        column.addWidget(self.pages, 1)
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.save = QPushButton("Сохранить")
        self.save.clicked.connect(self.economy.save)
        apply_role(self.save, "primary")
        self.data_action = QPushButton()
        apply_role(self.data_action, "primary")
        self.data_action.clicked.connect(self._trigger_data_action)
        self.dismiss = QPushButton("Закрыть")
        self.dismiss.clicked.connect(self.reject)
        for button in (rules.check, rules.apply, self.save, self.data_action, self.dismiss):
            footer.addWidget(button)
        column.addLayout(footer)
        outer.addLayout(column, 1)

        self.navigation.currentItemChanged.connect(self._select_item)
        for action in self._actions.values():
            action.changed.connect(self._update_data_action)
        self.select_section("rules")

    def select_section(self, section):
        self.navigation.setCurrentItem(self._sections[section])

    def _select_item(self, current, previous):
        section = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        if section not in SECTIONS:
            return
        self.section = section
        title, description = SECTIONS[section]
        self.title.setText(title)
        self.description.setText(description)
        rule_section = section == "rules"
        data_section = section in self._actions
        self.pages.setCurrentWidget(
            self.rules if rule_section else self.data_page if data_section else self.economy
        )
        self.rules.check.setVisible(rule_section)
        self.rules.apply.setVisible(rule_section)
        self.save.setVisible(not (rule_section or data_section))
        self.data_action.setVisible(data_section)
        if data_section:
            self._update_data_action()
        elif not rule_section:
            self.economy.select_section(section)

    def _update_data_action(self):
        if (action := self._actions.get(self.section)) is not None:
            self.data_action.setText(action.text())
            self.data_action.setEnabled(action.isEnabled())

    def _trigger_data_action(self):
        self._actions[self.section].trigger()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.navigation.setFixedWidth(152 if self.width() < 720 else 178)

    def may_close(self):
        focused = self.focusWidget()
        if focused and focused.hasFocus():
            focused.clearFocus()
        return self._force_close or not (self.rules.dirty or self.economy.dirty) or (
            QMessageBox.question(
                self, "Отбросить изменения настроек?",
                "Есть несохранённые изменения. Отбросить их и закрыть настройки?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes
        )

    def close_confirmed(self):
        self._force_close = True
        self.reject()

    def reject(self):
        if self.may_close():
            super().reject()

    def closeEvent(self, event):
        if not self.may_close():
            event.ignore()
            return
        self._force_close = True
        super().closeEvent(event)
