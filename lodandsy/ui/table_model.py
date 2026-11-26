"""An addressed Table view: stable UUID indexes and semantic edits, never per-key publication."""

import csv
import io
from dataclasses import replace
from html import escape
from uuid import uuid4

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QLineEdit, QStyledItemDelegate

from lodandsy.domain.table_document import display_value, parse_cell


class TableModel(QAbstractTableModel):
    document_changed = Signal(object)
    draft_changed = Signal()
    error = Signal(str)
    structure_changing = Signal()
    structure_changed = Signal()

    def __init__(self, document, drafts=None, parent=None, *, service=None):
        super().__init__(parent)
        self.document = document
        self.drafts = drafts if drafts is not None else {}
        self.service = service
        self._row_ids = [r.id for r in document.rows]
        self._column_ids = [c.id for c in document.columns]
        self._index_values()
        self._owners = set()
        self._local_edits = {}

    def _index_values(self):
        self._rows = {r.id: r for r in self.document.rows}
        self._columns = {c.id: c for c in self.document.columns}
        self._row_positions = {key: i for i, key in enumerate(self._row_ids)}
        self._column_positions = {key: i for i, key in enumerate(self._column_ids)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._row_ids)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._column_ids)

    def key(self, index):
        return self._row_ids[index.row()], self._column_ids[index.column()]

    def column(self, index):
        return self._columns[self._column_ids[index.column()]]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if (
            not index.isValid()
            or index.row() >= len(self._row_ids)
            or index.column() >= len(self._column_ids)
        ):
            return None
        row_id, col_id = self.key(index)
        row, col = self._rows.get(row_id), self._columns.get(col_id)
        if row is None or col is None:
            return None
        raw = row.value(col.id)
        draft = self.drafts.get((row.id, col.id))
        value, diagnostic, info = (
            self.service.cell_projection(self.document, row, col)
            if self.service
            else (raw, "", None)
        )
        if role == Qt.ItemDataRole.EditRole:
            return draft if draft is not None else display_value(raw)
        if role == Qt.ItemDataRole.DisplayRole:
            if draft is not None:
                return draft
            if diagnostic:
                return diagnostic
            if col.data_type == "entity_ref" and value is None:
                return "Выбрать предмет…" if col.ref_card_type == "item" else "Выбрать документ…"
            caption = self.service.cell_caption(self.document, row, col) if self.service else None
            if caption is not None:
                return caption
            return "—" if col.data_type == "projection" and value is None else display_value(value)
        if role == Qt.ItemDataRole.CheckStateRole and col.data_type == "bool":
            return (
                Qt.CheckState.PartiallyChecked
                if raw is None
                else Qt.CheckState.Checked
                if raw
                else Qt.CheckState.Unchecked
            )
        if role == Qt.ItemDataRole.BackgroundRole and draft is not None:
            return QColor("#542e32")
        if role == Qt.ItemDataRole.ForegroundRole and (diagnostic or col.data_type == "projection"):
            return QColor("#a6a6a3")
        if role == Qt.ItemDataRole.FontRole and col.data_type == "entity_ref" and info:
            font = QFont()
            font.setUnderline(True)
            return font
        if role == Qt.ItemDataRole.ToolTipRole:
            message = (
                self.service.draft_error(self.document.id, row.id, col.id)
                if draft is not None and self.service
                else diagnostic
            )
            if info:
                message = message or info.path + "\n" + info.id + "\nCtrl+Enter — открыть документ"
            return escape(
                message or "Ошибочный ввод не сохранён"
                if draft is not None
                else message or col.data_type
            )

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Vertical:
                return str(section + 1)
            return (
                self._columns[self._column_ids[section]].name
                if section < len(self._column_ids)
                else ""
            )
        if (
            role == Qt.ItemDataRole.ToolTipRole
            and orientation == Qt.Orientation.Horizontal
            and section < len(self._column_ids)
        ):
            return self._columns[self._column_ids[section]].data_type

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        column = self.column(index)
        if column.data_type not in {"projection", "entity_ref"}:
            flags |= Qt.ItemFlag.ItemIsEditable
        if column.data_type == "bool":
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role not in {
            Qt.ItemDataRole.EditRole,
            Qt.ItemDataRole.CheckStateRole,
        }:
            return False
        row, col = self.key(index)
        column = self.column(index)
        if column.data_type == "projection":
            self.error.emit("Вычисляемый столбец доступен только для чтения")
            return False
        try:
            parsed = (
                value in (Qt.CheckState.Checked, Qt.CheckState.Checked.value)
                if role == Qt.ItemDataRole.CheckStateRole
                else parse_cell(value, column.data_type)
            )
            updated = (
                self.service.request_cell_change(
                    self.document.id,
                    row,
                    col,
                    parsed,
                    parsed=True,
                    expected=self._rows[row].value(col),
                )
                if self.service
                else self.document.with_cell(row, col, parsed)
            )
        except ValueError as error:
            if self.service:
                self.service.reject_draft(self.document.id, row, col, str(value), error)
            else:
                self.drafts[(row, col)] = str(value)
                self.draft_changed.emit()
            self.error.emit(str(error))
            self.dataChanged.emit(index, index)
            return False
        had = self.drafts.pop((row, col), None) is not None
        if updated != self.document:
            self.set_document(updated)
            self.document_changed.emit(updated)
        if had:
            if self.service:
                self.service.notify_drafts(self.document.id)
            else:
                self.draft_changed.emit()
        self.dataChanged.emit(index, index)
        return True

    def apply(self, document):
        if document == self.document:
            return
        if self.service:
            document = self.service.update_table(document, expected=self.document)
        self.set_document(document)
        self.document_changed.emit(document)

    @staticmethod
    def _ranges(values):
        result = []
        for value in values:
            if result and result[-1][1] + 1 == value:
                result[-1] = (result[-1][0], value)
            else:
                result.append((value, value))
        return result

    def _reconcile(self, current, wanted, horizontal):
        wanted_set = set(wanted)
        remove = self.beginRemoveColumns if horizontal else self.beginRemoveRows
        removed = self.endRemoveColumns if horizontal else self.endRemoveRows
        insert = self.beginInsertColumns if horizontal else self.beginInsertRows
        inserted = self.endInsertColumns if horizontal else self.endInsertRows
        for first, last in reversed(
            self._ranges([i for i, key in enumerate(current) if key not in wanted_set])
        ):
            remove(QModelIndex(), first, last)
            del current[first : last + 1]
            removed()
        present = set(current)
        i = 0
        while i < len(wanted):
            if wanted[i] in present:
                i += 1
                continue
            start = i
            while i < len(wanted) and wanted[i] not in present:
                i += 1
            insert(QModelIndex(), start, i - 1)
            current[start:start] = wanted[start:i]
            inserted()

    def set_document(self, document):
        before = self.document
        if before is document or before == document:
            return
        old_rows = {r.id: r for r in before.rows}
        row_ids = [r.id for r in document.rows]
        col_ids = [c.id for c in document.columns]
        structural = before.columns != document.columns or self._row_ids != row_ids
        if structural:
            self.structure_changing.emit()
        self.document = document
        self._rows = {r.id: r for r in document.rows}
        self._columns = {c.id: c for c in document.columns}
        if structural:
            self._reconcile(self._column_ids, col_ids, True)
            self._reconcile(self._row_ids, row_ids, False)
            if self._row_ids != row_ids or self._column_ids != col_ids:
                self.layoutAboutToBeChanged.emit()
                indexes = self.persistentIndexList()
                keys = [self.key(index) for index in indexes]
                self._row_ids = row_ids
                self._column_ids = col_ids
                self._index_values()
                self.changePersistentIndexList(
                    indexes,
                    [
                        self.index(self._row_positions[row], self._column_positions[col])
                        for row, col in keys
                    ],
                )
                self.layoutChanged.emit()
            self._index_values()
            if col_ids:
                self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(col_ids) - 1)
            if row_ids:
                self.headerDataChanged.emit(Qt.Orientation.Vertical, 0, len(row_ids) - 1)
            self.structure_changed.emit()
        changes = set()
        for row in document.rows:
            old = old_rows.get(row.id)
            if old is row:
                continue
            for col in document.columns:
                if structural or old is None or old.value(col.id) != row.value(col.id):
                    changes.add((row.id, col.id))
                    changes.update(
                        (row.id, c.id)
                        for c in document.columns
                        if c.data_type == "projection" and c.source_column_id == col.id
                    )
        self.refresh_cells(changes)

    def refresh_cells(self, cells):
        for row, col in cells:
            if row in self._row_positions and col in self._column_positions:
                index = self.index(self._row_positions[row], self._column_positions[col])
                self.dataChanged.emit(index, index)

    def begin_editor(self, index):
        row, col = self.key(index)
        if self.service:
            owner = self.service.begin_edit(self.document.id, row, col)
            raw = self.service.edit_value(owner)
        else:
            owner = str(uuid4())
            raw = self.data(index, Qt.ItemDataRole.EditRole)
            self._local_edits[owner] = [row, col, self._rows[row].value(col), raw]
        self._owners.add(owner)
        return owner, raw

    def edit_text(self, owner, text):
        if self.service:
            self.service.edit_text(owner, text)
        elif owner in self._local_edits:
            self._local_edits[owner][3] = text

    def commit_editor(self, owner, *, finish=True):
        if self.service:
            success = self.service.commit_edit(owner, finish=finish)
        else:
            edit = self._local_edits.get(owner)
            if edit is None:
                return False
            row, col, base, raw = edit
            if row not in self._row_positions or col not in self._column_positions:
                self.error.emit("Ячейка удалена во время ввода")
                return False
            if self._rows[row].value(col) != base:
                self.drafts[(row, col)] = raw
                self.draft_changed.emit()
                self.error.emit("Ячейка изменена в другом представлении")
                return False
            success = self.setData(
                self.index(self._row_positions[row], self._column_positions[col]), raw
            )
            if not finish and success:
                edit[2] = self._rows[row].value(col)
            if finish:
                self._local_edits.pop(owner, None)
        if finish:
            self._owners.discard(owner)
        return success

    def cancel_editor(self, owner):
        if self.service:
            self.service.cancel_edit(owner)
        self._local_edits.pop(owner, None)
        self._owners.discard(owner)

    def flush_owned_edits(self):
        for owner in tuple(self._owners):
            self.commit_editor(owner, finish=False)

    def paste(self, start, text):
        if len(text.encode("utf-8")) > 2**20:
            raise ValueError("Вставка превышает 1 MiB")
        if not start.isValid() or not text:
            raise ValueError("Выберите начальную ячейку")
        document = self.document
        updates = {}
        affected = set()
        try:
            for y, line in enumerate(
                csv.reader(io.StringIO(text), delimiter="\t", strict=True), start.row()
            ):
                if y >= len(document.rows) or start.column() + len(line) > len(document.columns):
                    raise ValueError("Диапазон вставки выходит за таблицу")
                cells = dict(document.rows[y].cells)
                for x, value in enumerate(line, start.column()):
                    col = document.columns[x]
                    if col.data_type == "projection":
                        raise ValueError(
                            "Вставка затрагивает read-only проекцию; "
                            "выберите только редактируемый диапазон"
                        )
                    cells[col.id] = parse_cell(value, col.data_type)
                    affected.add((document.rows[y].id, col.id))
                updates[y] = replace(document.rows[y], cells=tuple(cells.items()))
        except csv.Error as error:
            raise ValueError("Некорректный или слишком большой TSV-фрагмент") from error
        updated = replace(
            document, rows=tuple(updates.get(y, row) for y, row in enumerate(document.rows))
        )
        self.apply(updated)
        cleared = False
        for key in affected:
            cleared |= self.drafts.pop(key, None) is not None
        if cleared:
            if self.service:
                self.service.notify_drafts(document.id)
            else:
                self.draft_changed.emit()


class SemanticCellDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        model = index.model()
        editor = QLineEdit(parent)
        editor.setMaxLength(65536)
        editor._table_model = model
        editor._edit_owner, raw = model.begin_editor(index)
        editor.setText(raw)
        editor._initialized = True
        editor._finished = False
        editor.textEdited.connect(lambda text: model.edit_text(editor._edit_owner, text))
        return editor

    def setEditorData(self, editor, index):
        if not getattr(editor, "_initialized", False):
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        model.edit_text(editor._edit_owner, editor.text())
        model.commit_editor(editor._edit_owner)
        editor._finished = True

    def eventFilter(self, editor, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            editor._table_model.cancel_editor(editor._edit_owner)
            editor._finished = True
        return super().eventFilter(editor, event)

    def destroyEditor(self, editor, index):
        if not getattr(editor, "_finished", True):
            editor._table_model.commit_editor(editor._edit_owner)
        super().destroyEditor(editor, index)
