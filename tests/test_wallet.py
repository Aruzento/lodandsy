from dataclasses import replace
from uuid import uuid4

import pytest
from PySide6.QtGui import QImage

from lodandsy.domain.currency import CUSTOM, RATE_SCALE, CoinAmount, CurrencySystem, Denomination
from lodandsy.domain.item_categories import ItemCategory

pytest_plugins = ["tests.project_fixture"]


def test_wallet_and_item_metadata_inherit_and_roundtrip(project, tmp_path):
    app, projects = project
    world = tmp_path / "Мир"
    assert projects.create_project(world)
    base = Denomination(str(uuid4()), "Луна", "л", RATE_SCALE)
    tiny = Denomination(str(uuid4()), "Искра", "и", 1)
    currency = CurrencySystem(CUSTOM, base.id, (base, tiny))
    category = ItemCategory(str(uuid4()), "Реликвии")
    app.economy.apply_settings(app.economy.settings, currency, (category,))
    owner = app.create_card("Страж", card_type="character")
    section = next(s for s in owner.sections if s.purpose == "inventory")
    template = app.actions.section_table(owner.id, section.id)
    template_wallet = (CoinAmount(base.id, 3), CoinAmount(tiny.id, 1))
    app.actions.set_wallet(template.id, template_wallet, expected=())
    first = app.cards_service.get_actor(app.cards_service.create_actor(owner.id))
    first_wallet = (CoinAmount(base.id, 1),)
    app.actions.set_wallet(first.inventory_id, first_wallet, expected=template_wallet)
    second = app.cards_service.get_actor(app.cards_service.create_actor(owner.id))
    assert app.tables_service.get_table(second.inventory_id).wallet == template_wallet
    assert app.tables.open_table(template.id).widget().wallet.total.text() == "3,00001 л"
    item = app.create_card("Реликвия", card_type="item")
    assert item.value("loot_enabled") is False
    app.cards_service.update_card_fields(item.id, {
        "cost": CoinAmount(tiny.id, 0), "weight": 1.5, "rarity": "Уникальный",
        "item_category": category.id, "loot_enabled": True,
    })
    with pytest.raises(ValueError, match="используется"):
        app.economy.apply_settings(app.economy.settings, replace(currency, denominations=(base,)),
                                   (category,))
    with pytest.raises(ValueError, match="Категория"):
        app.economy.apply_settings(app.economy.settings, currency, ())
    with pytest.raises(ValueError, match="Кошелёк изменился"):
        app.actions.set_wallet(first.inventory_id, (), expected=template_wallet)
    with pytest.raises(ValueError, match="только в инвентаре"):
        table = app.tables_service.create_table("Таблица")
        app.actions.set_wallet(table.id, template_wallet, expected=())
    assert projects.save_current()
    assert projects.create_project(tmp_path / "Другой мир", preserve_current=False)
    projects.open_project(world)
    assert app.economy.currency == currency
    assert app.economy.settings.custom_categories == (category,)
    assert app.cards_service.get_card(item.id).value("cost") == CoinAmount(tiny.id, 0)
    assert app.cards_service.get_card(item.id).value("rarity") == "Уникальный"
    assert app.tables_service.get_table(first.inventory_id).wallet == first_wallet
    assert app.tables_service.get_table(second.inventory_id).wallet == template_wallet


def test_player_placements_share_wallet_across_maps(project, tmp_path):
    app, projects = project
    projects.create_project(tmp_path / "world")
    player = app.create_card("Игрок", card_type="character", player=True)
    source = tmp_path / "map.png"
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    assert image.save(str(source))
    asset = projects.store.import_asset(source)
    projects.assets[asset.id] = asset
    first = app.maps_service.create_map("Первая", asset.id)
    second = app.maps_service.create_map("Вторая", asset.id)
    app.actions.place_card(first.id, player.id, 0, 0)
    app.actions.place_card(second.id, player.id, 0, 0)
    a, b = [app.maps_service.get_map(m.id).tokens[0] for m in (first, second)]
    assert a.actor_id == b.actor_id
    actor = app.cards_service.list_actors(player.id)[0]
    wallet = (CoinAmount(app.economy.currency.base_id, 125),)
    app.actions.set_wallet(actor.inventory_id, wallet, expected=())
    assert app.tables_service.get_table(actor.inventory_id).wallet == wallet
