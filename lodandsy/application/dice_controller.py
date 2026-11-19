"""An application tool; no entity, project, persistence or sibling controller dependency."""

from lodandsy.ui.dice_widget import DiceWidget


class DiceController:
    def __init__(self, windows):
        self.windows = windows
        self.runtime = {}

    def open(self):
        return self.windows.open_window("tool:dice", "Кубики", lambda: DiceWidget(self.runtime))
