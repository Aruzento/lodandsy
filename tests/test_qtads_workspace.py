import PySide6QtAds as ads
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.window_manager import WindowManager
from lodandsy.ui.workspace_placement import WorkspacePlacement


@pytest.fixture
def workspace(qtbot):
    shell = AppShell()
    qtbot.addWidget(shell)
    shell.show()
    return shell, WindowManager(shell)


@pytest.mark.parametrize("placement", list(WorkspacePlacement))
def test_all_initial_placements_have_live_content_and_nonzero_workspace(workspace, placement):
    shell, manager = workspace
    window = manager.open_window("one", "One", lambda: QLabel("Content"), placement)
    QApplication.processEvents()
    assert window.widget().text() == "Content"
    assert shell.workspace.width() > 0 and shell.workspace.height() > 0
    assert window.dock.isInFloatingContainer() == (placement == WorkspacePlacement.FLOATING)


def test_two_center_documents_tab_without_collapsing_drop_target(workspace):
    shell, manager = workspace
    a = manager.open_window("a", "A", lambda: QLabel("A"))
    b = manager.open_window("b", "B", lambda: QLabel("B"))
    QApplication.processEvents()
    assert a.dock.dockAreaWidget() is b.dock.dockAreaWidget()
    assert shell.workspace.width() > 0 and shell.workspace.height() > 0
    manager.close_window("a")
    assert b.dock in shell.workspace.dockWidgetsMap().values()


@pytest.mark.parametrize("area", [ads.LeftDockWidgetArea, ads.RightDockWidgetArea,
                                 ads.TopDockWidgetArea, ads.BottomDockWidgetArea])
def test_split_insert_and_redock_preserve_both_documents(workspace, area):
    shell, manager = workspace
    a = manager.open_window("a", "A", lambda: QLabel("A"))
    b = manager.open_window("b", "B", lambda: QLabel("B"))
    shell.workspace.addDockWidget(area, b.dock, a.dock.dockAreaWidget())
    QApplication.processEvents()
    assert a.dock.dockAreaWidget() is not b.dock.dockAreaWidget()
    b.dock.setFloating()
    QApplication.processEvents()
    floating = b.dock.floatingDockContainer()
    assert floating is not None and floating.isWindow()
    assert not floating.windowFlags() & Qt.WindowType.FramelessWindowHint
    floating.showMaximized()
    QApplication.processEvents()
    assert floating.isMaximized()
    floating.showNormal()
    shell.workspace.addDockWidget(area, b.dock, a.dock.dockAreaWidget())
    assert a.widget().text() == "A" and b.widget().text() == "B"


def test_restore_native_layout_and_clamp_lost_monitor(workspace):
    shell, manager = workspace
    a = manager.open_window("a", "A", lambda: QLabel("A"))
    b = manager.open_window("b", "B", lambda: QLabel("B"), WorkspacePlacement.FLOATING)
    QApplication.processEvents()
    b.dock.floatingDockContainer().move(100_000, 100_000)
    state = shell.workspace.saveState(1)
    assert shell.workspace.restoreState(state, 1)
    QApplication.processEvents()
    shell.workspace.ensure_visible()
    floating = b.dock.floatingDockContainer()
    assert any(s.availableGeometry().contains(floating.geometry().topLeft())
               for s in QApplication.screens())
    assert a.widget().text() == "A"
