import json
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from lodandsy.application.clipboard import (
    INVENTORY_MIME,
    clipboard_writer,
    decode_inventory_transfer,
    encode_inventory_transfer,
)
from lodandsy.domain.currency import CoinAmount
from lodandsy.domain.inventory_transfer import InventoryTransfer, ItemStack

pytest_plugins = ["tests.project_fixture"]


def create_inventory(app):
    owner = app.create_card("Персонаж", card_type="character")
    section = next(s for s in owner.sections if s.purpose == "inventory")
    return app.actions.section_table(owner.id, section.id)


def test_version_and_typed_mime_roundtrip(qtbot):
    transfer = InventoryTransfer(str(uuid4()), (ItemStack(str(uuid4()), 3),))
    writer = clipboard_writer()
    with qtbot.waitSignal(writer.message, timeout=10000) as copy_result:
        writer.copy("Копьё × 3", inventory=transfer)
    assert copy_result.args == ["Скопировано"]
    clipboard = QApplication.clipboard()
    assert clipboard.text() == "Копьё × 3"
    assert decode_inventory_transfer(bytes(clipboard.mimeData().data(INVENTORY_MIME))) == transfer
    broken = json.loads(encode_inventory_transfer(transfer))
    broken["version"] = True
    with pytest.raises(ValueError, match="версия"):
        decode_inventory_transfer(json.dumps(broken))
    broken["version"] = 1
    broken["items"][0]["count"] = 2.5
    with pytest.raises(ValueError, match="Количество"):
        decode_inventory_transfer(json.dumps(broken))
    broken["items"][0] = {"item_id": "bad-uuid", "count": 1}
    with pytest.raises(ValueError, match="UUID"):
        decode_inventory_transfer(json.dumps(broken))
    writer.copy("2d6 = 9")
    qtbot.waitUntil(lambda: clipboard.text() == "2d6 = 9")
    assert not clipboard.mimeData().hasFormat(INVENTORY_MIME)


def test_paste_confirmation_grouping_and_atomic_failure(project, qtbot, tmp_path, monkeypatch):
    app, projects = project
    root = tmp_path / "Первая игра"
    projects.create_project(root)
    identity = projects.store.project_id
    table = create_inventory(app)
    item = app.create_card("Сабля", card_type="item")
    base = app.economy.currency.base_id
    app.actions.set_wallet(table.id, (CoinAmount(base, 2),), expected=())
    original = app.tables_service.get_table(table.id)
    app._paste_inventory(table.id, InventoryTransfer(identity, (ItemStack(item.id, 1),)))
    existing = app.tables_service.get_table(table.id).rows[0]
    view = app.tables.open_table(table.id).widget()
    good = InventoryTransfer(
        identity, (ItemStack(item.id, 2), ItemStack(item.id, 3)), (CoinAmount(base, 4),)
    )
    writer = clipboard_writer()
    with qtbot.waitSignal(writer.message, timeout=10000) as copy_result:
        writer.copy("Сабля × 5\n4 зм", inventory=good)
    assert copy_result.args == ["Скопировано"]
    before = app.tables_service.get_table(table.id)
    guard = app.core.serial
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    view.paste_selection()
    assert app.core.serial == guard and app.tables_service.get_table(table.id) == before
    prompts = []

    def confirm(_parent, _title, prompt, *_buttons):
        prompts.append(prompt)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", confirm)
    app.window.show()
    qtbot.waitUntil(view.table.isVisible)
    view.table.setFocus()
    qtbot.keyClick(view.table, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert app.core.serial == guard + 1
    final = app.tables_service.get_table(table.id)
    assert final.rows[0] == existing
    row = tuple(final.rows[1].value(c.id) for c in final.columns)
    assert row == (item.id, 5, None, None, False)
    assert final.wallet == (CoinAmount(base, 6),) and original.wallet == (CoinAmount(base, 2),)
    assert "4 зм" in prompts[0]
    for invalid in (
        InventoryTransfer(str(uuid4()), good.items, good.coins),
        InventoryTransfer(identity, (*good.items, ItemStack(str(uuid4()), 1)), good.coins),
        InventoryTransfer(identity, good.items, (CoinAmount(str(uuid4()), 1),)),
    ):
        with pytest.raises(ValueError):
            app._paste_inventory(table.id, invalid)
        assert app.tables_service.get_table(table.id) == final
        assert app.core.serial == guard + 1
    plain = app.tables_service.create_table("Общая таблица")
    with pytest.raises(ValueError, match="только в инвентарь"):
        app._paste_inventory(plain.id, good)
    app.actions.delete_entity(item.id)
    with pytest.raises(ValueError, match="недоступен"):
        app._paste_inventory(table.id, good)
    assert app.tables_service.get_table(table.id) == final
    assert projects.save_current()
    projects.create_project(tmp_path / "Вторая игра", preserve_current=False)
    assert projects.store.project_id != identity
    projects.open_project(root)
    assert projects.store.project_id == identity
    QApplication.clipboard().clear()
