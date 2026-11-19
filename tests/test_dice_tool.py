import random
from contextlib import closing

import pytest

from lodandsy.application.sqlite_project_store import connect_database
from lodandsy.application.workspace_state import capture_workspace, restore_workspace
from lodandsy.domain.dice import DiceConfig, roll_dice

pytest_plugins = ["tests.project_fixture"]


def test_dice_tool_without_project_singleton_and_world_lifecycle(project, tmp_path):
    app, project = project
    window = app.modules.open_dice()
    assert app.modules.open_dice() is window
    assert app.window_manager.window_keys() == ("tool:dice",) or set(
        app.window_manager.window_keys()
    ) == {"tool:dice"}
    assert not app.session.entities.summaries() and not project.saver.dirty
    widget = window.widget()
    widget.counts[20].setValue(0)
    widget.counts[6].setValue(3)
    widget.modifier.setValue(-2)
    widget.throw()
    assert "d6:" in widget.result.toPlainText() and "Итог =" in widget.result.toPlainText()
    assert not hasattr(widget, "presets") and not project.saver.dirty
    project.create_project(tmp_path / "one", preserve_current=False)
    assert app.modules.open_dice() is window and widget.runtime["history"]
    with closing(connect_database(project.store.path, readonly=True)) as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='dice_document'"
            ).fetchall()
            == []
        )
        assert connection.execute("SELECT kind FROM entity").fetchall() == []
    state = capture_workspace(app)
    restore_workspace(app, state)
    assert len([k for k in app.window_manager.window_keys() if k == "tool:dice"]) == 1
    project.create_project(tmp_path / "two", preserve_current=False)
    assert app.modules.open_dice() is window
    for i in range(55):
        widget.throw()
    assert len(widget.runtime["history"]) == 50
    widget.clear_counts()
    widget.throw()
    assert widget.error.text() and not project.saver.dirty


def test_dice_engine_stays_independent_strict_and_repeatable():
    config = DiceConfig((0, 3, 0, 0, 0, 0, 0), -2)
    result = roll_dice(config, random.Random(4))
    assert result.groups == ((6, (2, 3, 1)),) and result.total == 4
    with pytest.raises(ValueError):
        roll_dice(DiceConfig((0,) * 7))
    with pytest.raises(ValueError):
        DiceConfig((True, 0, 0, 0, 0, 0, 0))
