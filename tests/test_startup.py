from PySide6.QtCore import QSize

from lodandsy.ui.app_shell import AppShell


def test_app_shell_starts(qtbot) -> None:
    window = AppShell()
    qtbot.addWidget(window)
    assert window.size() == QSize(1440, 960)

    window.show()

    assert window.isVisible()
    assert window.windowTitle() == "LODANDSY"
    # The native window manager may constrain the requested size to the screen.
    assert window.width() > 0 and window.height() > 0

    window.close()

    assert not window.isVisible()
