import csv
import io
from dataclasses import replace

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QApplication,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from lodandsy.application.clipboard import copy_text
from lodandsy.domain.table_document import ColumnDefinition, RowRecord, display_value, parse_cell
from lodandsy.ui.table_headers import TableView


class TableModel(QAbstractTableModel):
    document_changed = Signal(object)
    draft_changed = Signal()
    error = Signal(str)

    def __init__(self, document, drafts=None, parent=None):
        super().__init__(parent)
        self.document = document
        self.drafts = drafts if drafts is not None else {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.document.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.document.columns)

    def key(self, index):
        return self.document.rows[index.row()].id, self.document.columns[index.column()].id

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = self.document.rows[index.row()], self.document.columns[index.column()]
        value = row.value(col.id)
        draft = self.drafts.get((row.id, col.id))
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return draft if draft is not None else display_value(value)
        if role == Qt.ItemDataRole.CheckStateRole and col.data_type == "bool":
            return (
                Qt.CheckState.PartiallyChecked
                if value is None
                else Qt.CheckState.Checked
                if value
                else Qt.CheckState.Unchecked
            )
        if role == Qt.ItemDataRole.BackgroundRole and draft is not None:
            return QColor("#713d49")
        if role == Qt.ItemDataRole.ToolTipRole:
            return (
                "Ошибочный ввод не сохранён; исправьте или отмените. Другие данные сохраняются."
                if draft
                else col.data_type
            )

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                self.document.columns[section].name
                if orientation == Qt.Orientation.Horizontal
                else str(section + 1)
            )
        if role == Qt.ItemDataRole.ToolTipRole and orientation == Qt.Orientation.Horizontal:
            return self.document.columns[section].data_type

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = (
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        )
        if self.document.columns[index.column()].data_type == "bool":
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role not in (
            Qt.ItemDataRole.EditRole,
            Qt.ItemDataRole.CheckStateRole,
        ):
            return False
        row, col = self.key(index)
        try:
            parsed = (
                value == Qt.CheckState.Checked.value or value == Qt.CheckState.Checked
                if role == Qt.ItemDataRole.CheckStateRole
                else parse_cell(value, self.document.columns[index.column()].data_type)
            )
            updated = self.document.with_cell(row, col, parsed)
        except ValueError as error:
            self.drafts[(row, col)] = str(value)
            self.error.emit(str(error))
            self.draft_changed.emit()
            self.dataChanged.emit(index, index)
            return False
        had_draft = self.drafts.pop((row, col), None) is not None
        if updated != self.document:
            self.document = updated
            self.document_changed.emit(updated)
        if had_draft:
            self.draft_changed.emit()
        self.dataChanged.emit(index, index)
        return True

    def apply(self, document):
        if document != self.document:
            self.set_document(document)
            self.document_changed.emit(document)

    def set_document(self, document):
        before = self.document
        if document is before or document == before:
            return
        structural = document.columns != before.columns or tuple(
            r.id for r in document.rows
        ) != tuple(r.id for r in before.rows)
        if structural:
            self.beginResetModel()
        self.document = document
        if structural:
            valid_rows, valid_cols = {r.id for r in document.rows}, {c.id for c in document.columns}
            for key in list(self.drafts):
                if key[0] not in valid_rows or key[1] not in valid_cols:
                    del self.drafts[key]
            self.endResetModel()
        else:
            for y, (old, new) in enumerate(zip(before.rows, document.rows)):
                if old is new or old == new:
                    continue
                for x, column in enumerate(document.columns):
                    if old.value(column.id) != new.value(column.id):
                        index = self.index(y, x)
                        self.dataChanged.emit(index, index)

    def paste(self, start, text):
        if len(text.encode("utf-8")) > 2**20:
            raise ValueError("Вставка превышает 1 MiB")
        if not start.isValid() or not text:
            raise ValueError("Выберите начальную ячейку")
        values = csv.reader(io.StringIO(text), delimiter="\t", strict=True)
        document = self.document
        updates, affected = {}, set()
        try:
            for y, line in enumerate(values, start.row()):
                if y >= len(document.rows) or start.column() + len(line) > len(document.columns):
                    raise ValueError("Диапазон вставки выходит за таблицу")
                cells = dict(document.rows[y].cells)
                for x, text in enumerate(line, start.column()):
                    column = document.columns[x]
                    cells[column.id] = parse_cell(text, column.data_type)
                    affected.add((document.rows[y].id, column.id))
                updates[y] = replace(document.rows[y], cells=tuple(cells.items()))
        except csv.Error as error:
            raise ValueError("Некорректный или слишком большой TSV-фрагмент") from error
        # One validation and notification; no partially applied TSV.
        updated = replace(
            document, rows=tuple(updates.get(y, r) for y, r in enumerate(document.rows))
        )
        cleared = False
        for key in affected:
            cleared |= self.drafts.pop(key, None) is not None
        self.apply(updated)
        if cleared:
            self.draft_changed.emit()


class LiveCellDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setMaxLength(65536)
        row_id, column_id = index.model().key(index)
        model = index.model()

        def changed(text):
            row = next((i for i, r in enumerate(model.document.rows) if r.id == row_id), -1)
            col = next((i for i, c in enumerate(model.document.columns) if c.id == column_id), -1)
            if row >= 0 and col >= 0:
                model.setData(model.index(row, col), text)

        editor.textEdited.connect(changed)
        return editor


class TableWidget(QWidget):
    document_changed = Signal(object)
    draft_changed = Signal()

    def __init__(self, document, drafts=None):
        super().__init__()
        self.model = TableModel(document, drafts, self)
        self.model.document_changed.connect(self.document_changed)
        self.model.draft_changed.connect(self.draft_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.table = TableView()
        self.table.setModel(self.model)
        self.table.setItemDelegate(LiveCellDelegate(self.table))
        self.table.setAccessibleName("Таблица документов")
        self.table.horizontalHeader().setDefaultSectionSize(180)
        self.model.modelAboutToBeReset.connect(self._remember_ui)
        self.model.modelReset.connect(self._restore_ui)
        self._saved_ui = {}
        layout.addWidget(self.table, 1)
        self.discard = QPushButton("Отменить ошибочный ввод")
        self.discard.clicked.connect(self.discard_drafts)
        self.discard.hide()
        layout.addWidget(self.discard)
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setStyleSheet("color:#f19a9a")
        layout.addWidget(self.error)
        self.model.error.connect(self.error.setText)
        self.table.horizontalHeader().append_requested.connect(self.add_column)
        self.table.verticalHeader().append_requested.connect(self.add_row)
        self.table.horizontalHeader().customContextMenuRequested.connect(self._column_menu)
        self.table.verticalHeader().customContextMenuRequested.connect(self._row_menu)
        self.table.horizontalHeader().sectionMoved.connect(lambda *args: self._header_order(True))
        self.table.verticalHeader().sectionMoved.connect(lambda *args: self._header_order(False))
        self._reordering = False
        self.model.draft_changed.connect(self.update_draft_notice)
        self.update_draft_notice()
        for label, shortcut, callback in [
            ("Копировать ячейки", QKeySequence.StandardKey.Copy, self.copy_selection),
            ("Вставить TSV", QKeySequence.StandardKey.Paste, self.paste_selection),
        ]:
            action = QAction(label, self)
            action.setShortcut(shortcut)
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(callback)
            self.table.addAction(action)

    def set_document(self, document):
        self.model.set_document(document)

    def ui_state(self):
        index = self.table.currentIndex()
        return {
            "widths": {
                c.id: self.table.columnWidth(i) for i, c in enumerate(self.model.document.columns)
            },
            "selected": list(self.model.key(index)) if index.isValid() else None,
        }

    def restore_ui(self, state):
        if not isinstance(state, dict):
            return
        widths = state.get("widths", {})
        if isinstance(widths, dict):
            for i, c in enumerate(self.model.document.columns):
                width = widths.get(c.id)
                if type(width) is int and 24 <= width <= 2000:
                    self.table.setColumnWidth(i, width)
        selected = state.get("selected")
        if isinstance(selected, list) and len(selected) == 2:
            rows, columns = self.model.document.rows, self.model.document.columns
            row = next((i for i, r in enumerate(rows) if r.id == selected[0]), -1)
            col = next((i for i, c in enumerate(columns) if c.id == selected[1]), -1)
            if row >= 0 and col >= 0:
                self.table.setCurrentIndex(self.model.index(row, col))

    def _remember_ui(self):
        self._saved_ui = self.ui_state()

    def _restore_ui(self):
        self.restore_ui(self._saved_ui)

    def discard_drafts(self):
        self.model.drafts.clear()
        self.revert_active_editor()
        self.error.clear()
        self.model.layoutChanged.emit()
        self.draft_changed.emit()

    def revert_active_editor(self):
        for editor in self.table.findChildren(QLineEdit):
            self.table.closeEditor(editor, QAbstractItemDelegate.EndEditHint.RevertModelCache)

    def _confirm(self, occupied):
        return (
            not occupied
            or QMessageBox.question(
                self, "Удаление", "Удалить выбранные данные? Это действие нельзя отменить."
            )
            == QMessageBox.StandardButton.Yes
        )

    def add_row(self):
        doc = self.model.document
        self.model.apply(replace(doc, rows=(*doc.rows, RowRecord(len(doc.rows)))))
        if doc.columns:
            self.table.setCurrentIndex(self.model.index(len(doc.rows), 0))
            self.table.scrollTo(self.table.currentIndex())

    def remove_row(self):
        index = getattr(self, "_context_row", None)
        index = self.table.currentIndex().row() if index is None else index
        doc = self.model.document
        if index >= 0 and self._confirm(bool(doc.rows[index].cells)):
            self.model.apply(
                replace(
                    doc,
                    rows=tuple(
                        replace(r, position=i)
                        for i, r in enumerate(r for r in doc.rows if r.id != doc.rows[index].id)
                    ),
                )
            )

    def add_column(self):
        name, ok = QInputDialog.getText(self, "Колонка", "Название:")
        if not ok or not name.strip():
            return
        kind, ok = QInputDialog.getItem(self, "Тип", "Тип:", ["text", "number", "bool"], 0, False)
        if ok:
            doc = self.model.document
            self._apply(
                lambda: replace(
                    doc, columns=(*doc.columns, ColumnDefinition(name, kind, len(doc.columns)))
                )
            )
            if doc.rows:
                self.table.setCurrentIndex(self.model.index(0, len(doc.columns)))
                self.table.scrollTo(self.table.currentIndex())

    def edit_column(self):
        index = getattr(self, "_context_column", None)
        index = self.table.currentIndex().column() if index is None else index
        doc = self.model.document
        if index < 0:
            return
        column = doc.columns[index]
        name, ok = QInputDialog.getText(self, "Колонка", "Название:", text=column.name)
        if not ok or not name.strip():
            return
        kinds = ["text", "number", "bool"]
        kind, ok = QInputDialog.getItem(
            self, "Тип", "Тип:", kinds, kinds.index(column.data_type), False
        )
        if not ok:
            return

        def update():
            changed = replace(column, name=name, data_type=kind)
            # Strict change: incompatible existing values are rejected, never dropped/coerced.
            return replace(
                doc, columns=tuple(changed if c.id == column.id else c for c in doc.columns)
            )

        self._apply(update)

    def remove_column(self):
        index = getattr(self, "_context_column", None)
        index = self.table.currentIndex().column() if index is None else index
        doc = self.model.document
        if index < 0:
            return
        key = doc.columns[index].id
        if self._confirm(any(r.value(key) is not None for r in doc.rows)):
            columns = tuple(
                replace(c, position=i) for i, c in enumerate(c for c in doc.columns if c.id != key)
            )
            rows = tuple(
                replace(r, cells=tuple((k, v) for k, v in r.cells if k != key)) for r in doc.rows
            )
            self.model.apply(replace(doc, columns=columns, rows=rows))

    def _header_order(self, horizontal):
        if self._reordering:
            return
        doc = self.model.document
        header = self.table.horizontalHeader() if horizontal else self.table.verticalHeader()
        current = doc.columns if horizontal else doc.rows
        order = [header.logicalIndex(i) for i in range(header.count())]
        if order == list(range(len(current))):
            return
        self._reordering = True
        try:
            values = tuple(replace(current[old], position=i) for i, old in enumerate(order))
            self.model.apply(replace(doc, **{"columns" if horizontal else "rows": values}))
            header.reset()
        finally:
            self._reordering = False

    def _column_menu(self, point):
        header = self.table.horizontalHeader()
        index = header.logicalIndexAt(point)
        menu = QMenu(self)
        menu.addAction("Добавить столбец…", self.add_column)
        if index >= 0:
            self._context_column = index
            menu.addAction("Название и тип…", self.edit_column)
            menu.addAction("Удалить столбец…", self.remove_column)
        menu.exec(header.mapToGlobal(point))
        self._context_column = None

    def _row_menu(self, point):
        header = self.table.verticalHeader()
        index = header.logicalIndexAt(point)
        menu = QMenu(self)
        menu.addAction("Добавить строку", self.add_row)
        if index >= 0:
            self._context_row = index
            menu.addAction("Удалить строку…", self.remove_row)
        menu.exec(header.mapToGlobal(point))
        self._context_row = None

    def update_draft_notice(self):
        invalid = bool(self.model.drafts)
        self.discard.setVisible(invalid)
        if not invalid:
            self.error.clear()
        else:
            self.error.setText("Ошибочный ввод не сохранён. Другие данные можно сохранять.")

    def copy_selection(self):
        indexes = self.table.selectionModel().selectedIndexes()
        if not indexes:
            return
        rows, cols = [i.row() for i in indexes], [i.column() for i in indexes]
        stream = io.StringIO()
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        for y in range(min(rows), max(rows) + 1):
            writer.writerow(
                [self.model.data(self.model.index(y, x)) for x in range(min(cols), max(cols) + 1)]
            )
        copy_text(stream.getvalue().rstrip("\n"))

    def paste_selection(self):
        self._apply(
            lambda: self.model.paste(self.table.currentIndex(), QApplication.clipboard().text())
        )

    def _apply(self, operation):
        try:
            result = operation()
            if result is not None:
                self.model.apply(result)
            self.error.clear()
        except ValueError as error:
            self.error.setText(str(error))
