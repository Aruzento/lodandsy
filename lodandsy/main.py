import sys

from PySide6.QtWidgets import QApplication

from lodandsy.application.app_controller import AppController
from lodandsy.ui.app_shell import AppShell


def main() -> int:
    app = QApplication(sys.argv)

    window = AppShell()

    _controller = AppController(window)

    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())