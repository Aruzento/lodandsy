from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from lodandsy.domain.table_document import ColumnDefinition, RowRecord, TableDocument
from lodandsy.ui.table_widget import TableWidget


def test_real_header_append_controls_never_become_cells_and_empty_table(qtbot, monkeypatch):
    document = TableDocument("Table", columns=(), rows=())
    widget = TableWidget(document)
    qtbot.addWidget(widget)
    widget.resize(600, 400)
    widget.show()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Item", True))
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("text", True))
    qtbot.mouseClick(widget.table.horizontalHeader().plus, Qt.MouseButton.LeftButton)
    assert widget.model.columnCount() == 1 and widget.model.rowCount() == 0
    qtbot.mouseClick(widget.table.verticalHeader().plus, Qt.MouseButton.LeftButton)
    assert widget.model.rowCount() == 1 and widget.model.columnCount() == 1
    assert not hasattr(widget, "roll_requested") and not hasattr(document, "choose")
    assert widget.model.setData(widget.model.index(0, 0), "Sword")
    assert widget.model.document.rows[0].value(widget.model.document.columns[0].id) == "Sword"
    assert (
        widget.table.horizontalHeader().count() == 1 and widget.table.verticalHeader().count() == 1
    )
    # Footer controls remain outside the canonical/TSV model even after scrolling.
    widget.resize(260, 240)
    qtbot.wait(10)
    widget.table.horizontalScrollBar().setValue(widget.table.horizontalScrollBar().maximum())
    button = widget.table.horizontalHeader().plus
    assert button.x() + button.width() <= widget.table.horizontalHeader().viewport().width() + 1
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)

    def delete_column():
        menu = QApplication.activePopupWidget()
        assert menu is not None
        next(a for a in menu.actions() if a.text() == "Удалить столбец…").trigger()
        menu.close()

    QTimer.singleShot(0, delete_column)
    widget._column_menu(QPoint(3, 3))
    assert widget.model.columnCount() == 0


def test_two_header_drag_orders_are_canonical_and_ids_stable(qtbot):
    columns = (ColumnDefinition("A"), ColumnDefinition("B", position=1))
    rows = (RowRecord(0, ((columns[0].id, "A0"),)), RowRecord(1, ((columns[1].id, "B1"),)))
    widget = TableWidget(TableDocument("Table", columns=columns, rows=rows))
    qtbot.addWidget(widget)
    widget.table.horizontalHeader().moveSection(0, 1)
    assert [c.id for c in widget.model.document.columns] == [columns[1].id, columns[0].id]
    widget.table.verticalHeader().moveSection(0, 1)
    assert [r.id for r in widget.model.document.rows] == [rows[1].id, rows[0].id]
    assert {cell for row in widget.model.document.rows for cell in row.cells} == {
        cell for row in rows for cell in row.cells
    }
