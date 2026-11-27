import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from lodandsy import APP_VERSION
from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName("LODANDSY")
    app.setApplicationName("LODANDSY")
    app.setApplicationVersion(APP_VERSION)
    apply_theme(app)
    parser = argparse.ArgumentParser(description="LODANDSY")
    parser.add_argument("--version", action="version", version=f"LODANDSY {APP_VERSION}")
    parser.add_argument("project", nargs="?", type=Path)
    args = parser.parse_args()

    window = AppShell()

    _controller = AppController(window)
    _project = ProjectController(_controller)

    if args.project:
        try:
            _project.open_project(args.project)
        except (OSError, ValueError) as error:
            _project._show_error(error)
            return 1
        window.show()
    elif not _project.choose_project(welcome=True):
        _project.can_close()
        return 0

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
