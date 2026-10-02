from PySide6.QtCore import QPoint
from PySide6.QtGui import QContextMenuEvent

from lodandsy.domain.card import Card
from lodandsy.ui.card_tree_model import CardTreeModel
from lodandsy.ui.card_tree_view import CardTreeView


def test_context_menu_event_emits_clicked_index(
    qtbot,
) -> None:
    card = Card(title="World")

    model = CardTreeModel()
    model.set_cards([card])

    view = CardTreeView()
    qtbot.addWidget(view)

    view.setModel(model)
    view.show()

    index = model.index(0, 0)

    position = view.visualRect(index).center()

    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse,
        position,
        QPoint(100, 100),
    )

    with qtbot.waitSignal(
        view.context_menu_requested,
        timeout=1000,
    ) as signal:
        view.contextMenuEvent(event)

    emitted_index = signal.args[0]

    assert emitted_index.isValid()
    assert emitted_index.data() == "World"