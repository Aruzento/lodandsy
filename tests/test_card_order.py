import pytest
from PySide6.QtCore import QModelIndex, Qt

from lodandsy.application.app_controller import AppController
from lodandsy.domain.card_collection import CardCollection
from lodandsy.ui.app_shell import AppShell


def test_reorder_and_reparent_share_domain_validation_and_preserve_sibling_order():
    cards = CardCollection()
    a, b, c = [cards.create(title) for title in ["A", "B", "C"]]
    cards.update(c.id, position=0)
    assert cards.child_ids(None) == (c.id, a.id, b.id)
    cards.update(a.id, parent_id=c.id, position=0)
    assert cards.child_ids(None) == (c.id, b.id)
    assert cards.child_ids(c.id) == (a.id,)
    assert [summary.position for summary in cards.summaries()] == [0, 0, 1]
    for changes in [{"position": -1}, {"position": 10}, {"position": True},
                    {"parent_id": a.id, "position": 0}]:
        before = cards.all()
        with pytest.raises(ValueError):
            cards.update(c.id, **changes)
        assert cards.all() == before


def test_real_tree_drop_reorders_domain_and_keeps_selection(qtbot):
    window = AppShell()
    qtbot.addWidget(window)
    controller = AppController(window)
    a, b = controller.create_card("A"), controller.create_card("B")
    panel = window.tree_panel
    panel.tree_view.setCurrentIndex(panel.tree_model.index_for_card(a.id))
    mime = panel.tree_model.mimeData([panel.tree_model.index_for_card(a.id)])
    assert panel.tree_model.dropMimeData(mime, Qt.DropAction.MoveAction, 2, 0, QModelIndex())
    assert controller.cards.child_ids(None) == (b.id, a.id)
    assert panel.tree_model.index(0, 0).data() == "B"
    assert controller.session.current_card_id == a.id
