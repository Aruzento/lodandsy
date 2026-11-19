from pathlib import Path
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from lodandsy.application.cards_service import CardsService
from lodandsy.application.mow_import import (
    PreparedImport,
    apply_import,
    frontmatter,
    inspect_source,
    prepare_import,
    source_image,
)
from lodandsy.application.rich_html import html_text
from lodandsy.application.sqlite_project_store import ProjectSnapshot, SQLiteProjectStore
from lodandsy.domain.card import Card
from lodandsy.domain.card_collection import CardCollection

REAL = Path("docs/iterations/2026-11-19-iteration-4/references/1790538099148-2682f598.md")


def fixture(path, id, parent=None, order=0, body="", extra=""):
    # Synthetic MOW fixtures, deliberately distinct from the supplied real sample.
    path.write_text(
        f"---\nid: {id}\nschemaVersion: 1\nparent: {parent or 'null'}\norder: {order}\n"
        "tags: [card, creature]\naliases: [Alias]\ntype: creature\ntemplate: card\n---\n"
        + f'<div data-card-shell="v1"><h1>Card {order}</h1>'
        '<div class="card-short-description rich-text-field">Summary</div>'
        '<div class="entity-main"><div class="template-block" data-block-type="text" '
        'data-block-version="1"><h2>Описание</h2>'
        f'<div class="rich-text-field">{body}</div></div></div>{extra}</div>',
        encoding="utf-8",
    )


def test_supplied_real_sample_actual_id_title_type_empty_body_and_parent(tmp_path, qapp):
    before = REAL.read_bytes()
    plan = inspect_source(REAL)
    assert not plan.errors, plan.report()
    assert plan.records[0].metadata["id"] == "24acd7ea-c76c-439c-afc3-5c46560fcaf0"
    store = SQLiteProjectStore.create(tmp_path / "world")
    prepared = prepare_import(plan, store, (), ())
    (card,) = prepared.cards
    assert card.title == "Существа.Тюрьма - подземка" and card.card_type == "folder"
    assert "tags" not in dict(card.values) and not hasattr(card, "template_id")
    assert any("tags" in w for w in prepared.warnings)
    assert not html_text(card.content).strip() and card.portrait is None
    assert card.parent_id is None and any("parent" in w for w in prepared.warnings)
    assert "select" not in card.content and "Изображение" not in card.content
    assert REAL.read_bytes() == before
    store.close()


def test_two_pass_links_order_media_repeat_and_backup(tmp_path, qapp):
    source = tmp_path / "source"
    source.mkdir()
    root, child1, child2 = [str(uuid4()) for _ in range(3)]
    image = QImage(20, 10, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.red)
    image.save(str(source / "portrait.png"))
    fixture(
        source / "root.md",
        root,
        body=f'<a class="wiki-link" data-page-id="{child1}">Readable</a>'
        "<script>danger</script><select><option>character</option></select>"
        '<span data-runtime="true">runtime</span>',
    )
    fixture(
        source / "b.md",
        child1,
        root,
        20,
        '<b>Body</b><img src="portrait.png"><img src="https://invalid.test/a.png">',
        extra='<div class="media-box is-portrait"><img src="portrait.png" alt="Portrait"></div>',
    )
    fixture(source / "a.md", child2, root, 10, "<i>First</i>")
    plan = inspect_source(source)
    store = SQLiteProjectStore.create(tmp_path / "world")
    prepared = prepare_import(plan, store, (), ())
    session = CardsService(CardCollection())
    apply_import(session, prepared)
    cards = session.cards.all()
    parent = next(c for c in cards if c.value("mow_id") == root)
    child = next(c for c in cards if c.value("mow_id") == child1)
    assert f"lodandsy://entity/{child.id}" in parent.content
    assert (
        "danger" not in parent.content
        and "runtime" not in parent.content
        and "character" not in parent.content
    )
    assert len(prepared.assets) == 1 and child.portrait.asset_id == prepared.assets[0].id
    assert child.value("aliases") == ("Alias",)
    assert any("portrait description/caption" in w for w in prepared.warnings)
    assert not child.section(
        next(s.id for s in child.sections if s.purpose == "inventory")
    ).table_id
    assert [
        session.cards.get(i).value("mow_id") for i in session.entities.child_ids(parent.id)
    ] == [child2, child1]
    repeat = prepare_import(plan, store, cards, prepared.assets)
    assert not repeat.cards and not repeat.assets
    copies = prepare_import(plan, store, cards, prepared.assets, conflicts="remap")
    assert len(copies.cards) == 3 and not {c.id for c in copies.cards} & {c.id for c in cards}
    store.save(ProjectSnapshot(cards, 1, prepared.assets))
    backup = tmp_path / "world.lodbackup"
    store.backup(backup)
    restored = SQLiteProjectStore.restore(backup, tmp_path / "restore")
    assert restored.load().cards == store.load().cards
    restored.close()
    store.close()


@pytest.mark.parametrize(
    "header",
    ["x: !!python/object:evil", "x: &a [a]", "x: [[[[a]]]]", "x: 1\nx: 2", "x:\n  - nested"],
)
def test_unsafe_or_unsupported_yaml_is_rejected(header):
    with pytest.raises(ValueError):
        frontmatter("---\n" + header + "\n---\nbody")


def test_cycles_duplicates_corrupt_and_atomic_rollback(tmp_path, qapp):
    source = tmp_path / "source"
    source.mkdir()
    a, b = str(uuid4()), str(uuid4())
    fixture(source / "a.md", a, b)
    fixture(source / "b.md", b, a)
    assert any("Цикл" in e for e in inspect_source(source).errors)
    fixture(source / "b.md", a)
    assert any("Повторный" in e for e in inspect_source(source).errors)
    session = CardsService(CardCollection())
    original = session.create_card("Preserved")
    one = Card("Valid")
    invalid = Card("Invalid", parent_id=str(uuid4()))
    before = session.entities.summaries()
    with pytest.raises(ValueError):
        apply_import(session, PreparedImport((one, invalid), (), ()))
    assert session.entities.summaries() == before and session.cards.get(original.id) == original


@pytest.mark.parametrize(
    "value",
    [
        "../outside.png",
        "%2e%2e/outside.png",
        "https://invalid.test/img",
        "file:///C:/a.png",
        "C:/a.png",
        "x\\y.png",
        "//host/a.png",
    ],
)
def test_media_path_escape_and_remote_are_blocked(tmp_path, value):
    with pytest.raises((ValueError, OSError)):
        source_image(tmp_path, value)


def test_junction_source_image_cannot_escape(tmp_path):
    native = pytest.importorskip("_winapi")
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.png").write_bytes(b"secret")
    native.CreateJunction(str(outside), str(source / "linked"))
    with pytest.raises(ValueError):
        source_image(source, "linked/secret.png")


def test_failed_prepare_removes_only_its_unpublished_assets(tmp_path, qapp):
    source = tmp_path / "source"
    source.mkdir()
    image = QImage(10, 10, QImage.Format.Format_RGB32)
    image.fill(0xFF224466)
    image.save(str(source / "image.png"))
    fixture(source / "card.md", str(uuid4()), body='<img src="image.png">')
    # Invalid final canonical summary after a successfully staged image.
    path = source / "card.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("Summary", "x" * 600), encoding="utf-8"
    )
    store = SQLiteProjectStore.create(tmp_path / "world")
    with pytest.raises(ValueError):
        prepare_import(inspect_source(source), store, (), ())
    assert not tuple((store.root / "assets").iterdir())
    assert not store.load().cards
    store.close()
