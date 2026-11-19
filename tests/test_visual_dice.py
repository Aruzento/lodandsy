from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from lodandsy.application.dice_payload_codec import decode_dice, encode_dice
from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.domain.dice_document import FACES, DiceConfig, DiceDocument, DicePreset, roll_dice

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


def test_mixed_rng_bounds_d100_zero_and_codec():
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
    document = DiceDocument("Mixed", presets=(DicePreset("Roll", config),))
    assert decode_dice(document.title, document.id, 2, encode_dice(document)) == document
    with pytest.raises(ValueError):
        replace(document, presets=(document.presets[0], document.presets[0]))
    with pytest.raises(ValueError):
        decode_dice(document.title, document.id, 1, "1d20")


def test_presets_independent_roll_clean_runtime_bounded_reopen_and_backup(
    project, qtbot, tmp_path, monkeypatch
):
    app, project = project
    project.create_project(tmp_path / "world")
    first = app.modules.session.create_dice("First")
    second = app.modules.session.create_dice("Second")
    widget = app.modules.open_dice(first.id).widget()
    other = app.modules.open_dice(second.id).widget()
    widget.counts[6].setValue(2)
    widget.modifier.setValue(-3)
    config = widget.current_preset().config
    assert other.current_preset().config == DiceConfig()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Mixed", True))
    widget.rename_preset()
    widget.duplicate_preset()
    assert len(widget.document.presets) == 2
    assert widget.document.presets[0].id != widget.document.presets[1].id
    assert widget.current_preset().config == config
    widget.add_preset()
    assert len(widget.document.presets) == 3
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No)
    widget.delete_preset()
    assert len(widget.document.presets) == 3
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    widget.delete_preset()
    assert len(widget.document.presets) == 2
    widget.presets.setCurrentIndex(0)
    assert project.save_current()
    revision = project.saver.revision
    for _ in range(55):
        widget.throw()
    assert project.saver.revision == revision and not project.saver.dirty
    assert len(widget.runtime["history"]) == 50
    widget.copy.click()
    assert QApplication.clipboard().text() == widget.runtime["last"]
    app.window_manager.close_window(f"dice:{first.id}")
    widget = app.modules.open_dice(first.id).widget()
    assert len(widget.runtime["history"]) == 50
    before = project.store.load()
    archive = tmp_path / "backup.zip"
    project.store.backup(archive)
    restored = SQLiteProjectStore.restore(archive, tmp_path / "restored")
    assert restored.load() == before
    restored.close()
    project.open_project(tmp_path / "restored")
    widget = app.modules.open_dice(first.id).widget()
    assert not widget.runtime.get("history")
    assert widget.document.presets[0].config == config
    widget.clear_counts()
    assert not sum(widget.current_preset().config.counts)
    widget.throw()
    assert "хотя бы" in widget.error.text()


def test_invalid_large_preset_name_and_count_edits_never_escape_ui(project, monkeypatch):
    app, _ = project
    widget = app.modules.open_dice().widget()
    before = widget.document
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("X" * 201, True))
    widget.add_preset()
    widget.rename_preset()
    assert widget.document == before and widget.error.text()
    widget.counts[20].setValue(1000)
    widget.counts[6].setValue(1)
    assert sum(widget.current_preset().config.counts) == 1000
    assert widget.counts[6].value() == 0 and widget.error.text()
    assert tuple(widget.counts) == FACES
