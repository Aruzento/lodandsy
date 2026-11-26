from random import Random
from uuid import uuid4

from lodandsy.domain.currency import CoinAmount
from lodandsy.domain.item_categories import STANDARD_CATEGORIES
from lodandsy.domain.treasure import CatalogItem, ShopParameters, generate_shop

pytest_plugins = ["tests.project_fixture"]


def test_shop_unique_assortment_at_scale_and_small_pool():
    category = STANDARD_CATEGORIES[0].id
    items = tuple(
        CatalogItem(str(uuid4()), f"Предмет {i}", category if i < 80 else None, None, None, False)
        for i in range(120)
    )
    assert ShopParameters().minimum == 20 and ShopParameters().maximum == 50
    result = generate_shop(items, ShopParameters(50, 50, category), Random(2))
    assert result.available == 80 and len(set(result.item_ids)) == 50
    assert set(result.item_ids) <= {item.id for item in items[:80]}
    tiny = generate_shop(items[:3], ShopParameters(), Random(2))
    assert len(tiny.item_ids) == tiny.available == 3 < tiny.requested
    assert not generate_shop((), ShopParameters(), Random(2)).item_ids


def test_native_shop_reopens_and_shows_live_item_data(project, tmp_path):
    app, projects = project
    assert app.shop.open() is None and not projects.shop_action.isEnabled()
    root = tmp_path / "Мир магазина"
    assert projects.create_project(root)
    category = STANDARD_CATEGORIES[0].id
    first = app.create_card("Клинок", card_type="item")
    base = app.economy.currency.base_id
    app.cards_service.update_card_fields(first.id, {
        "item_category": category, "loot_enabled": False, "weight": 2, "cost": CoinAmount(base, 4),
    })
    item = app.create_card("Без цены", card_type="item")
    app.cards_service.update_card_fields(item.id, {"item_category": category, "loot_enabled": True})
    app.create_card("Заметка", card_type="note")
    projects.shop_action.trigger()
    opened = app.window_manager.find_window(app.shop.key)
    assert app.shop.open() is opened
    view = opened.widget()
    view.category.setCurrentIndex(view.category.findData(category))
    revision = app.core.serial
    view.generate_button.click()
    assert app.core.serial == revision
    assortment = app.shop.result
    assert set(assortment.item_ids) == {first.id, item.id}
    assert "доступно 2" in view.summary.text()
    assert "Без цены: 1" in view.summary.text()
    assert projects.save_current()
    assert projects.create_project(tmp_path / "Иной мир", preserve_current=False)
    assert app.shop.result is None and app.window_manager.find_window(app.shop.key) is None
    projects.open_project(root)
    assert app.shop.result == assortment and app.shop.parameters.category == category
    view = app.shop.open().widget()
    row = assortment.item_ids.index(first.id)
    app.cards_service.update_card_fields(first.id, {"cost": CoinAmount(base, 7)})
    assert view.results.item(row, 1).text() == "7 зм"
    view.results.cellClicked.emit(row, 0)
    assert app.window_manager.find_window(app.card_editor_window_key(first.id))
    app.actions.delete_entity(first.id)
    assert "недоступен" in view.results.item(row, 0).text()
