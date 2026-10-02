from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget

from lodandsy.ui.app_shell import AppShell


def test_app_shell_has_expected_structure(qtbot) -> None:
    window = AppShell()
    qtbot.addWidget(window)
    window.show()

    assert window.centralWidget() is window.central_surface

    assert (
        window.toolBarArea(window.left_rail)
        == Qt.ToolBarArea.LeftToolBarArea
    )
    assert (
        window.toolBarArea(window.right_rail)
        == Qt.ToolBarArea.RightToolBarArea
    )

    assert not window.left_rail.isMovable()
    assert not window.left_rail.isFloatable()
    assert not window.right_rail.isMovable()
    assert not window.right_rail.isFloatable()

    assert (
        window.dockWidgetArea(window.tree_panel)
        == Qt.DockWidgetArea.LeftDockWidgetArea
    )
    assert (
        window.dockWidgetArea(window.inspector_panel)
        == Qt.DockWidgetArea.RightDockWidgetArea
    )

    assert (
        window.tree_panel.features()
        == QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
    )
    assert (
        window.inspector_panel.features()
        == QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
    )


def test_side_panels_can_be_toggled(qtbot) -> None:
    window = AppShell()
    qtbot.addWidget(window)
    window.show()

    assert window.tree_panel.isVisible()
    assert window.inspector_panel.isVisible()

    window.left_rail.tree_action.trigger()
    window.right_rail.inspector_action.trigger()

    assert not window.tree_panel.isVisible()
    assert not window.inspector_panel.isVisible()

    window.left_rail.tree_action.trigger()
    window.right_rail.inspector_action.trigger()

    assert window.tree_panel.isVisible()
    assert window.inspector_panel.isVisible()