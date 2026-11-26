from PySide6.QtCore import QPoint
from PySide6.QtGui import QContextMenuEvent

from lodandsy.domain.card import Card
from lodandsy.domain.document_payloads import project_entities
from lodandsy.ui.card_tree_view import CardTreeView
from lodandsy.ui.project_tree_model import ProjectTreeModel


def test_context_menu_event_emits_clicked_index(
    qtbot,
) -> None:
    card = Card(title="World")

    model = ProjectTreeModel()
    model.set_entities(project_entities([card]).summaries())

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


def test_keyboard_context_menu_uses_current_row(qtbot):
    model = ProjectTreeModel()
    model.set_entities(project_entities([Card("First"), Card("Second")]).summaries())
    view = CardTreeView()
    qtbot.addWidget(view)
    view.setModel(model)
    view.show()
    first, second = [model.index(i, 0) for i in range(2)]
    view.setCurrentIndex(second)
    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Keyboard, view.visualRect(first).center(), QPoint(100, 100),
    )
    with qtbot.waitSignal(view.context_menu_requested) as signal:
        view.contextMenuEvent(event)
    anchor = view.viewport().mapToGlobal(view.visualRect(second).bottomLeft())
    assert signal.args == [second, anchor]
