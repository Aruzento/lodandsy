import pytest

from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.ui.app_shell import AppShell


@pytest.fixture
def project(qtbot):
    window = AppShell()
    qtbot.addWidget(window, before_close_func=lambda widget: setattr(widget, "close_guard", None))
    controller = AppController(window)
    project = ProjectController(controller)
    yield controller, project
    window.close_guard = None
    controller.modules.shutdown()
    project.saver.shutdown()
    if project.store:
        project.store.close()
