from dataclasses import replace
from uuid import uuid4

import pytest

from lodandsy.application.card_payload_codec import decode_card, encode_card
from lodandsy.application.rich_html import text_document
from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.domain.card import EMPTY_DOCUMENT, Card, Portrait
from lodandsy.domain.card_schema import FIELD_DEFINITIONS
from lodandsy.ui.card_search_dialog import CardSearchDialog

pytest_plugins = ["tests.project_fixture"]


def test_fields_roundtrip_unset_false_zero_refs_and_type_change():
    card = Card("Canon", card_type="character", portrait=Portrait())
    card = card.with_fields(
        {
            "name": "Same title",
            "summary": "Summary",
            "hp": 0,
            "ac": None,
            "featured": False,
            "aliases": ("A",),
            "related_entity": str(uuid4()),
            "token_image": str(uuid4()),
        }
    )
    assert card.value("title") == card.value("name") == "Same title"
    assert card.value("hp") == 0 and card.value("featured") is False
    assert card.value("ac") is None and card.value("speed") is None
    assert card.content == card.value("description") == EMPTY_DOCUMENT
    changed = replace(card, card_type="article")
    assert changed.sections == card.sections and changed.values == card.values
    version, data = encode_card(changed)
    assert version == 4 and decode_card(changed.title, card.id, None, version, data) == changed


@pytest.mark.parametrize(
    "key,value",
    [
        ("unknown", 1),
        ("hp", True),
        ("hp", float("nan")),
        ("cost", -1),
        ("featured", 0),
        ("aliases", ["x"]),
        ("token_cells_w", 1.5),
        ("token_kind", "rpg"),
        ("token_image", "../x"),
        ("summary", "x" * 501),
    ],
)
def test_invalid_field_patch_cannot_publish_partial_change(project, key, value):
    app, _ = project
    card = app.create_card("Before", card_type="character")
    changes = []
    app.session.card_changed.connect(lambda *args: changes.append(args))
    with pytest.raises(ValueError):
        app.session.update_card_fields(card.id, {"title": "After", key: value})
    assert app.cards.get(card.id) == card and not changes


def test_session_addressed_events_search_and_backup(project, tmp_path, qtbot):
    app, project = project
    project.create_project(tmp_path / "world")
    card = app.create_card("Character", card_type="character")
    events = []
    app.session.card_changed.connect(lambda *args: events.append(args))
    app.session.update_card_fields(
        card.id,
        {
            "summary": "River guardian",
            "hp": 0,
        },
    )
    assert events[-1] == (card.id, frozenset({"summary", "hp"}))
    notes = card.sections[-1]
    app.session.update_section(card.id, notes.id, content=text_document("A quiet hero"))
    assert notes.id in events[-1][1]
    search = CardSearchDialog(app.session)
    qtbot.addWidget(search)
    search.query.setText("guardian")
    search.refresh()
    assert search.results.count() == 1
    assert project.save_current()
    snapshot = project.store.load()
    assert snapshot.cards == app.cards.all()
    backup = tmp_path / "copy.zip"
    project.store.backup(backup)
    restored = SQLiteProjectStore.restore(backup, tmp_path / "restored")
    assert restored.load() == snapshot
    restored.close()
    app.session.update_card(card.id, card_type="note")
    assert app.cards.get(card.id).value("hp") == 0


def test_unknown_duplicate_or_unsafe_card_payload_refuses():
    import json

    card = Card("A")
    version, source = encode_card(card)
    data = json.loads(source)
    data["fields"]["unknown"] = "bad"
    with pytest.raises(ValueError):
        decode_card(card.title, card.id, None, version, json.dumps(data))
    with pytest.raises(ValueError):
        decode_card(
            card.title,
            card.id,
            None,
            version,
            source.replace('"fields": {}', '"fields": {}, "fields": {}'),
        )
    with pytest.raises(ValueError):
        card.with_fields({"name": "A", "title": "B"})
    assert set(FIELD_DEFINITIONS) >= {
        "hp",
        "ac",
        "speed",
        "rarity",
        "weight",
        "cost",
        "region",
        "climate",
        "danger_level",
    }


def test_card_title_constraint_is_enforced_on_creation_and_generic_entity_rename(qapp):
    from lodandsy.application.application_session import ApplicationSession
    from lodandsy.domain.card_collection import CardCollection

    session = ApplicationSession(CardCollection())
    with pytest.raises(ValueError):
        session.create_card("x" * 2001)
    card = session.create_card("Preserved")
    before = session.entities.summaries()
    with pytest.raises(ValueError):
        session.update_entity(card.id, title="x" * 2001)
    assert session.entities.summaries() == before and session.cards.get(card.id) == card
