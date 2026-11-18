import sys

from PySide6.QtWidgets import QApplication

from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)

    window = AppShell()

    _controller = AppController(window)
    _project = ProjectController(_controller)

    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
