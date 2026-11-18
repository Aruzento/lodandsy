from dataclasses import FrozenInstanceError
from uuid import UUID, uuid4

import pytest

from lodandsy.domain.card import Card
from lodandsy.domain.card_collection import CardCollection


def test_loaded_collection_rejects_duplicates_missing_parent_and_cycles():
    first_id, second_id = str(uuid4()), str(uuid4())
    card = Card("A", id=first_id)
    with pytest.raises(ValueError, match="unique"):
        CardCollection([card, card])
    with pytest.raises(ValueError, match="Unknown card"):
        CardCollection([Card("A", parent_id=second_id)])
    with pytest.raises(ValueError, match="cycle"):
        CardCollection([
            Card("A", id=first_id, parent_id=second_id),
            Card("B", id=second_id, parent_id=first_id),
        ])


def test_collection_exposes_only_immutable_snapshots():
    cards = CardCollection()
    original = cards.create("A")
    for card in [original, cards.get(original.id), *cards.all()]:
        with pytest.raises(FrozenInstanceError):
            card.parent_id = str(uuid4())
    updated = cards.update(original.id, title="B", content="Text")
    assert original.title == "A"
    assert cards.get(original.id) is updated
    assert updated.id == original.id
    assert updated.title == "B"
    assert updated.content == "Text"


def test_rejected_updates_leave_payload_and_child_index_unchanged():
    cards = CardCollection()
    root = cards.create("Root")
    child = cards.create("Child", root.id)
    for changes in [
        {"title": ""}, {"id": str(uuid4())}, {"content": None},
        {"title": "Changed", "parent_id": child.id},
        {"title": "Changed", "parent_id": str(uuid4())},
    ]:
        with pytest.raises(ValueError):
            cards.update(root.id, **changes)
        assert cards.get(root.id) is root
        assert cards.child_ids(None) == (root.id,)
        assert cards.child_ids(root.id) == (child.id,)


def test_index_tracks_reparent_delete_and_repeated_moves():
    cards = CardCollection()
    a, b = cards.create("A"), cards.create("B")
    child = cards.create("Child", a.id)
    leaf = cards.create("Leaf", child.id)
    for parent_id in [b.id, None, a.id, a.id, b.id]:
        cards.reparent(child.id, parent_id)
        for candidate in [None, a.id, b.id]:
            assert (child.id in cards.child_ids(candidate)) == (candidate == parent_id)
        assert cards.descendant_ids(child.id) == (leaf.id,)
    assert cards.delete(b.id) == (b.id, child.id, leaf.id)
    assert cards.child_ids(None) == (a.id,)
    assert cards.descendant_ids(a.id) == ()


def test_deep_loaded_tree_traversal_and_delete_do_not_scan_or_recurse():
    ids = [str(UUID(int=i + 1)) for i in range(10_000)]
    cards = CardCollection(
        Card(str(i), id=card_id, parent_id=ids[i - 1] if i else None)
        for i, card_id in enumerate(ids)
    )

    class NoFullScan(dict):
        def values(self):
            pytest.fail("Subtree operations must use the child index")

    cards._cards = NoFullScan(cards._cards)
    assert cards.descendant_ids(ids[0]) == tuple(ids[1:])
    assert cards.delete(ids[0]) == tuple(ids)
    assert cards.child_ids(None) == ()


def test_generated_duplicate_is_rejected_without_changing_index(monkeypatch):
    cards = CardCollection()
    existing = cards.create("A")
    monkeypatch.setattr("lodandsy.domain.card.uuid4", lambda: UUID(existing.id))
    with pytest.raises(ValueError, match="unique"):
        cards.create("B")
    assert cards.all() == (existing,)
    assert cards.child_ids(None) == (existing.id,)
