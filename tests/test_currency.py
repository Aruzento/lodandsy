from dataclasses import replace
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.domain.currency import (
    CUSTOM,
    RATE_SCALE,
    CurrencySystem,
    Denomination,
    format_rate,
    parse_rate,
)

pytest_plugins = ["tests.project_fixture"]


def denomination(name, abbreviation, rate):
    return Denomination(str(uuid4()), name, abbreviation, parse_rate(rate))


def test_standard_rates_and_stable_ids():
    system = CurrencySystem()
    assert system.base.abbreviation == "зм"
    rates = [d.rate_units for d in system.denominations]
    assert rates == [1_000_000, 100_000, 50_000, 10_000, 1000]
    assert system == CurrencySystem()
    with pytest.raises(ValueError, match="фиксированы"):
        replace(system, denominations=system.denominations[:-1])


@pytest.mark.parametrize("text", ["0", "-1", "0,000001", "NaN", "3e2", "1,2.3", "1000001"])
def test_invalid_rates(text):
    with pytest.raises(ValueError):
        parse_rate(text)


def test_small_exact_rate_and_used_denomination_guard():
    base = denomination("Луна", "л", "1")
    small = denomination("Искра", "и", "0,00001")
    assert small.rate_units * RATE_SCALE == base.rate_units
    assert format_rate(small.rate_units) == "0,00001"
    assert format_rate(parse_rate("0.50000")) == "0,5"
    assert format_rate(base.rate_units) == "1"
    system = CurrencySystem(CUSTOM, base.id, (base, small))
    renamed = replace(small, name="Осколок")
    system.validate_change(replace(system, denominations=(base, renamed)), {small.id})
    changed = replace(small, rate_units=2)
    system.validate_change(replace(system, denominations=(base, changed)), {base.id})
    with pytest.raises(ValueError, match="Искра"):
        system.validate_change(replace(system, denominations=(base, changed)), {small.id})
    with pytest.raises(ValueError, match="Искра"):
        system.validate_change(replace(system, denominations=(base,)), {small.id})
    with pytest.raises(ValueError, match="Систему"):
        system.validate_change(CurrencySystem(), {base.id})


def test_base_and_duplicate_labels_are_validated():
    base = denomination("Луна", "л", "1")
    small = denomination("Искра", "и", "0.00001")
    with pytest.raises(ValueError, match="базовой"):
        CurrencySystem(CUSTOM, small.id, (base, small))
    with pytest.raises(ValueError, match="уникальными"):
        CurrencySystem(CUSTOM, base.id, (base, replace(small, abbreviation="Л")))


def test_currency_editor_and_project_backup(project, qtbot, tmp_path):
    app, projects = project
    assert not app.economy_action.isEnabled()
    path = tmp_path / "Экономика"
    assert projects.create_project(path)
    assert app.economy_action.isEnabled()
    dialog = app.open_economy()
    assert app.open_economy() is dialog
    assert dialog.table.rowCount() == 5
    dialog.system.setCurrentIndex(dialog.system.findData(CUSTOM))
    assert dialog.table.rowCount() == 1
    assert not dialog.table.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable
    qtbot.mouseClick(dialog.add_button, Qt.MouseButton.LeftButton)
    dialog.table.closePersistentEditor(dialog.table.item(1, 0))
    dialog.table.setCurrentCell(1, 1)
    dialog.table.item(1, 0).setText("Искра")
    dialog.table.item(1, 1).setText("и")
    dialog.table.item(1, 2).setText("0,00001")
    qtbot.mouseClick(app.settings_window.save, Qt.MouseButton.LeftButton)
    expected = app.economy.currency
    assert expected.kind == CUSTOM
    assert expected.denominations[1].rate_units == 1
    app.cards_service.apply_rules(app.cards_service.preview_rules(()))
    assert app.economy.currency == expected
    assert projects.save_current()
    backup = tmp_path / "Экономика.lodbackup"
    projects.store.backup(backup)
    other = tmp_path / "Другой мир"
    assert projects.create_project(other, preserve_current=False)
    assert app.economy.currency == CurrencySystem()
    projects.open_project(path)
    assert app.economy.currency == expected
    restored = SQLiteProjectStore.restore(backup, tmp_path / "Восстановлен")
    try:
        snapshot = restored.load()
        assert snapshot.currency == expected
        assert snapshot.rules.revision == 1
    finally:
        restored.close()


def test_gear_settings_keep_drafts_until_project_switch_is_confirmed(
    project, qtbot, tmp_path, monkeypatch,
):
    app, projects = project
    assert projects.create_project(tmp_path / "Первый")
    qtbot.mouseClick(app.window.right_rail.settings_button, Qt.MouseButton.LeftButton)
    window = app.settings_window
    assert window.section == "rules"
    assert app.open_settings("currency") is window
    window.economy.system.setCurrentIndex(window.economy.system.findData(CUSTOM))
    window.select_section("categories")
    window.select_section("backup")
    assert window.data_action.isVisible()
    window.select_section("currency")
    assert window.economy.system.currentData() == CUSTOM
    assert app.economy.currency.kind != CUSTOM
    monkeypatch.setattr(QMessageBox, "question", lambda *_, **__: QMessageBox.StandardButton.No)
    assert not projects.create_project(tmp_path / "Второй", preserve_current=False)
    assert app.settings_window is window
    assert window.economy.dirty
    monkeypatch.setattr(QMessageBox, "question", lambda *_, **__: QMessageBox.StandardButton.Yes)
    assert projects.create_project(tmp_path / "Второй", preserve_current=False)
    assert app.settings_window is None
    assert app.economy.currency == CurrencySystem()
