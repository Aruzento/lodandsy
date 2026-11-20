from dataclasses import replace

import pytest
from PySide6.QtWidgets import QComboBox

from lodandsy.domain.card import Card, Portrait
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.card_editor import CardEditorWidget

pytest_plugins = ["tests.project_fixture"]


def test_immutable_type_in_collection_and_generic_payload():
    cards = CardCollection()
    card = cards.create("Fixed", card_type="character")
    with pytest.raises(ValueError):
        cards.update(card.id, card_type="item")
    with pytest.raises(ValueError):
        cards.entities.put_payload(card.id, replace(card.payload(), card_type="item"))
    assert cards.get(card.id) == card


@pytest.mark.parametrize("width", [380, 620, 1200])
def test_header_geometry_content_independent_tabs_and_no_gutter(qtbot, width):
    page = CardEditorWidget()
    qtbot.addWidget(page)
    page.resize(width, 650)
    page.show()
    sizes = []
    for i in range(5):
        card = Card(
            "Short" if i % 2 else "Long title " * 60, portrait=Portrait() if i % 2 else None
        )
        card = card.with_fields({"summary": "Summary " * (1 if i % 2 else 60)})
        page.set_canonical(card)
        qtbot.waitUntil(lambda: page.header.width() == page.width())
        sizes.append((page.header.height(), page.portrait_panel.size()))
        for section in card.sections:
            page.select_section(section.id)
            assert page.portrait_panel.size() == sizes[-1][1]
        assert page.portrait_panel.x() < page.metadata.x()
        assert page.type_label.y() < page.title_edit.y() < page.summary_edit.y()
        assert page.text_edit.mapTo(page, page.text_edit.rect().topLeft()).x() == 16
        assert not page.header.findChildren(QComboBox)
        assert not hasattr(page, "breadcrumb") and not hasattr(page, "summary_expand")
    assert all(size == sizes[0] for size in sizes)
    assert 132 <= page.portrait_panel.width() <= 220


def test_five_real_documents_switch_resize_and_project_reopen(project, tmp_path, qtbot):
    from PySide6.QtGui import QImage

    from lodandsy.application.sqlite_project_store import SQLiteProjectStore

    app, project = project
    app.window.show()
    root = tmp_path / "Мир карточек"
    project.create_project(root)
    image = QImage(200, 200, QImage.Format.Format_RGB32)
    image.fill(0xFF667788)
    source = tmp_path / "portrait.png"
    image.save(str(source))
    asset = project.store.import_asset(source)
    project.assets[asset.id] = asset
    cards = []
    for i in range(5):
        card = app.create_card("Коротко" if i % 2 else "Длинное название " * 20)
        app.cards_service.update_card_fields(
            card.id, {"summary": "Описание " * (1 if i % 2 else 50)}
        )
        if i % 2:
            app.cards_service.update_card(card.id, portrait=Portrait(asset.id))
        cards.append(card)
    for width in (1000, 1600, 1100):
        app.window.resize(width, 900)
        sizes = {}
        for card in (*cards, *reversed(cards)):
            page = app.open_card_editor(card.id).widget()
            qtbot.waitUntil(lambda: page.isVisible())
            size = (page.header.height(), page.portrait_panel.size())
            if card.id in sizes:
                assert sizes[card.id] == size
            sizes[card.id] = size
            for section in app.cards.get(card.id).sections:
                page.select_section(section.id)
                assert page.portrait_panel.size() == size[1]
    assert project.save_current()
    another = SQLiteProjectStore.create(tmp_path / "Other")
    another.close()
    project.open_project(tmp_path / "Other")
    project.open_project(root)
    for card in cards:
        page = app.open_card_editor(card.id).widget()
        assert page.title_edit.text() == card.title
        assert 132 <= page.portrait_panel.width() <= 220
