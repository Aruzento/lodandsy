"""Economy settings use the project's existing transaction and save pipeline."""

from dataclasses import replace

from PySide6.QtCore import QObject, Signal

from lodandsy.domain.project_settings import ProjectSettings


class EconomyService(QObject):
    changed = Signal()

    def __init__(self, core, used_denominations, parent=None):
        super().__init__(parent)
        self.core = core
        self.used_denominations = used_denominations

    @property
    def settings(self):
        return self.core.entities.settings or ProjectSettings()

    @property
    def currency(self):
        return self.settings.currency

    def apply_settings(self, previous, currency, categories):
        current = self.settings
        if (previous.currency, previous.custom_categories) != (
            current.currency, current.custom_categories
        ):
            raise ValueError("Экономика уже изменилась. Откройте настройки заново.")
        candidate = replace(current, currency=currency, custom_categories=categories)
        if current == candidate:
            return
        current.currency.validate_change(currency, self.used_denominations())
        with self.core.transaction():
            self.core.entities.put_settings(candidate)
            self.core.after_commit(self.changed.emit)
            self.core.mark_changed()
