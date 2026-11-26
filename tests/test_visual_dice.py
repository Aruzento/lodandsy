import pytest
from PySide6.QtWidgets import QApplication

from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.domain.dice import FACES, DiceConfig, roll_dice

pytest_plugins = ["tests.project_fixture"]


@pytest.mark.parametrize(
    "counts,modifier",
    [
        ((0,) * 6, 0),
        ((-1,) * 7, 0),
        ((True, 0, 0, 0, 0, 0, 0), 0),
        ((1001, 0, 0, 0, 0, 0, 0), 0),
        ((600, 500, 0, 0, 0, 0, 0), 0),
        ((0,) * 7, True),
        ((0,) * 7, 10**10),
    ],
)
def test_dice_config_bounds(counts, modifier):
    with pytest.raises(ValueError):
        DiceConfig(counts, modifier)


def test_mixed_rng_bounds_d100_zero():
    class MaximumRng:
        def __init__(self):
            self.calls = []

        def randint(self, low, high):
            self.calls.append((low, high))
            return high

    rng = MaximumRng()
    config = DiceConfig((1, 2, 0, 0, 0, 1, 1), -3)
    result = roll_dice(config, rng)
    assert result.groups == ((4, (4,)), (6, (6, 6)), (20, (20,)), (100, (100,)))
    assert result.total == 133
    assert rng.calls == [(1, 4), (1, 6), (1, 6), (1, 20), (1, 100)]
    with pytest.raises(ValueError, match="хотя бы"):
        roll_dice(DiceConfig((0,) * 7))


def test_roll_clean_runtime_bounded_reopen_and_backup(project, tmp_path, qtbot):
    app, project = project
    project.create_project(tmp_path / "world")
    widget = app.dice.open().widget()
    widget.counts[6].setValue(2)
    widget.modifier.setValue(-3)
    config = widget.runtime["config"]
    assert project.save_current()
    revision = project.saver.revision
    for _ in range(55):
        widget.throw()
    assert project.saver.revision == revision and not project.saver.dirty
    assert len(widget.runtime["history"]) == 50
    from lodandsy.application.clipboard import clipboard_writer

    with qtbot.waitSignal(clipboard_writer().message, timeout=5000) as copied:
        widget.copy.click()
    assert copied.args == ["Скопировано"]
    assert QApplication.clipboard().text() == widget.runtime["last"]
    app.window_manager.close_window("tool:dice")
    widget = app.dice.open().widget()
    assert len(widget.runtime["history"]) == 50
    before = project.store.load()
    archive = tmp_path / "backup.zip"
    project.store.backup(archive)
    restored = SQLiteProjectStore.restore(archive, tmp_path / "restored")
    assert restored.load() == before
    restored.close()
    project.open_project(tmp_path / "restored")
    assert app.dice.open().widget() is widget
    assert widget.runtime["config"] == config
    widget.clear_counts()
    assert not sum(widget.runtime["config"].counts)
    widget.throw()
    assert "хотя бы" in widget.error.text()


def test_invalid_count_edits_never_escape_ui(project):
    app, _ = project
    widget = app.dice.open().widget()
    widget.counts[20].setValue(1000)
    widget.counts[6].setValue(1)
    assert sum(widget.runtime["config"].counts) == 1000
    assert widget.counts[6].value() == 0 and widget.error.text()
    assert tuple(widget.counts) == FACES
