from PySide6.QtCore import QSize

from lodandsy.ui.app_shell import AppShell


def test_app_shell_starts(qtbot) -> None:
    window = AppShell()
    qtbot.addWidget(window)

    window.show()

    assert window.isVisible()
    assert window.windowTitle() == "LODANDSY"
    assert window.size() == QSize(1280, 800)

    window.close()

    assert not window.isVisible()