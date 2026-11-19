from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget

from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.workspace_host import WorkspaceHost


def test_app_shell_has_expected_structure(qtbot):
    window = AppShell()
    qtbot.addWidget(window)
    window.show()
    assert window.centralWidget() is window.workspace
    assert isinstance(window.workspace, WorkspaceHost)
    for toolbar in [window.left_rail, window.right_rail]:
        assert not toolbar.isMovable()
        assert not toolbar.isFloatable()
    for panel in [window.tree_host, window.inspector_host]:
        assert panel.features() == QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
    assert window.dockWidgetArea(window.tree_host) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert window.dockWidgetArea(window.inspector_host) == Qt.DockWidgetArea.RightDockWidgetArea
    assert window.tree_panel.features() == QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
    assert window.inspector_panel.features() == QDockWidget.DockWidgetFeature.NoDockWidgetFeatures


def test_side_panels_can_be_toggled(qtbot):
    window = AppShell()
    qtbot.addWidget(window)
    window.show()
    window.left_rail.tree_action.trigger()
    window.right_rail.inspector_action.trigger()
    assert not window.tree_host.isVisible()
    assert not window.inspector_host.isVisible()
    window.left_rail.tree_action.trigger()
    window.right_rail.inspector_action.trigger()
    assert window.tree_host.isVisible()
    assert window.inspector_host.isVisible()
