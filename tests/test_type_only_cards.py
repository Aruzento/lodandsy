from dataclasses import replace

import pytest

from lodandsy.application.card_payload_codec import decode_card, encode_card
from lodandsy.application.cards_service import CardsService
from lodandsy.domain.card import Card, Portrait
from lodandsy.domain.card_collection import CardCollection
from lodandsy.domain.card_schema import CARD_TYPES, FIELD_DEFINITIONS, available_fields

pytest_plugins = ["tests.project_fixture"]


def test_real_inspector_add_offers_only_absent_allowed_fields_and_type_hides_old_fields(
    project, monkeypatch
):
    from PySide6.QtWidgets import QInputDialog

    app, _ = project
    card = app.create_card("Character", card_type="character")
    app.cards_service.select_card(card.id)
    app.cards_service.update_card_fields(card.id, {"hp_max": 15})
    labels = []

    def select(parent, title, label, items, *args):
        labels.extend(items)
        return "Важная карточка", True

    monkeypatch.setattr(QInputDialog, "getItem", select)
    app.window.inspector_panel.add_field.click()
    assert (
        "Максимум хитов" not in labels and "Важная карточка" in labels and "Редкость" not in labels
    )
    assert app.cards.get(card.id).value("hp_max") == 15
    with pytest.raises(ValueError):
        app.cards_service.update_card(card.id, card_type="article")
    assert "hp_max" not in app.window.inspector_panel.field_form.controls
    editor = app.card_views.open_game_sheet(card.id).widget()
    assert "hp_max" in editor.game_sheet.controls
    assert app.cards.get(card.id).value("hp_max") == 15


def test_type_only_fields_roundtrip_and_no_loss():
    assert "tags" not in FIELD_DEFINITIONS
    card = Card("Character", card_type="character").with_fields(
        {"hp_max": 15, "aliases": ("Alias",)}
    )
    with pytest.raises(ValueError):
        replace(card, card_type="article")
    changed = card
    assert changed.sections == card.sections and changed.value("hp_max") == 15
    version, data = encode_card(changed)
    assert version == 6 and "template_id" not in data and '"tags"' not in data
    assert decode_card(changed.title, changed.id, None, version, data) == changed
    with pytest.raises(ValueError):
        decode_card(card.title, card.id, None, 3, data)
    with pytest.raises(ValueError):
        card.with_fields({"tags": ("old",)})
    assert not hasattr(card, "template_id")


def test_repeated_add_field_is_rejected_in_domain_and_session(qapp):
    session = CardsService(CardCollection())
    card = session.create_card("Character", card_type="character")
    session.add_card_field(card.id, "hp_max")
    session.update_card_fields(card.id, {"hp_max": 15})
    before = session.cards.get(card.id)
    assert "hp_max" not in {f.key for f in available_fields(before)}
    with pytest.raises(ValueError):
        session.add_card_field(card.id, "hp_max")
    assert session.cards.get(card.id) == before and before.value("hp_max") == 15
    with pytest.raises(ValueError):
        session.add_card_field(card.id, "rarity")


def test_portrait_has_one_explicit_media_contract():
    card = Card("Card")
    portrait = Portrait()
    assert card.with_portrait(portrait).portrait is portrait
    with pytest.raises(ValueError):
        card.with_fields({"portrait": None})
    for invalid in [(0, 0, 0, 1), (0.5, 0, 0.6, 1), (float("nan"), 0, 1, 1)]:
        with pytest.raises(ValueError):
            Portrait(crop=invalid)


@pytest.mark.parametrize("kind", tuple(CARD_TYPES))
def test_all_types_create_without_template(kind):
    card = Card("Card", card_type=kind)
    assert card.sections[0].purpose == "description"
    assert len({s.id for s in card.sections}) == len(card.sections)
