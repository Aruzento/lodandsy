import csv
import io
from dataclasses import replace

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QApplication,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lodandsy.application.clipboard import INVENTORY_MIME, copy_text, decode_inventory_transfer
from lodandsy.domain.table_document import ColumnDefinition
from lodandsy.ui.conflict_bar import ConflictBar
from lodandsy.ui.entity_picker import EntityPicker
from lodandsy.ui.table_headers import TableView
from lodandsy.ui.table_model import SemanticCellDelegate, TableModel
from lodandsy.ui.wallet_widget import WalletWidget


class TableWidget(QWidget):
    document_changed = Signal(object)
    draft_changed = Signal()

    def __init__(
        self, document, drafts=None, *, service=None, open_entity=None, set_wallet=None,
        paste_inventory=None,
    ):
        super().__init__()
        self.model = TableModel(document, drafts, self, service=service)
        self.references = service.references if service else None
        self.open_entity = open_entity or (lambda kind, key: None)
        self.paste_inventory = paste_inventory
        self.model.document_changed.connect(self.document_changed)
        self.model.draft_changed.connect(self.draft_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.wallet = None
        if set_wallet is not None:
            self.wallet = WalletWidget(
                lambda: service.currency, lambda: self.model.document, set_wallet, self
            )
            layout.addWidget(self.wallet)
        self.table = TableView()
        self.table.setModel(self.model)
        self.table.setItemDelegate(SemanticCellDelegate(self.table))
        self.table.setAccessibleName("Таблица документов")
        self.table.horizontalHeader().setDefaultSectionSize(180)
        for position, column in enumerate(document.columns):
            if column.key in {"item", "quantity", "description", "cost"}:
                self.table.setColumnWidth(
                    position,
                    {"item": 210, "quantity": 96, "description": 300, "cost": 116}[column.key],
                )
        self.model.structure_changing.connect(self._remember_ui)
        self.model.structure_changed.connect(self._restore_ui)
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
        self.conflicts = ConflictBar(self)
        self.conflicts.resolve_requested.connect(self._resolve_conflict)
        layout.addWidget(self.conflicts)
        self.model.error.connect(self.error.setText)
        self.table.horizontalHeader().append_requested.connect(self.add_column)
        self.table.verticalHeader().append_requested.connect(self.add_row)
        self.table.horizontalHeader().customContextMenuRequested.connect(self._column_menu)
        self.table.verticalHeader().customContextMenuRequested.connect(self._row_menu)
        self.table.horizontalHeader().sectionMoved.connect(lambda *args: self._header_order(True))
        self.table.verticalHeader().sectionMoved.connect(lambda *args: self._header_order(False))
        self.table.installEventFilter(self)
        self.table.viewport().installEventFilter(self)
        self.table.doubleClicked.connect(self._activate_reference)
        self._reordering = False
        self.model.draft_changed.connect(self.update_draft_notice)
        self.update_draft_notice()
        for label, shortcut, callback in [
            ("Копировать ячейки", QKeySequence.StandardKey.Copy, self.copy_selection),
            ("Вставить", QKeySequence.StandardKey.Paste, self.paste_selection),
        ]:
            action = QAction(label, self)
            action.setShortcut(shortcut)
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(callback)
            self.table.addAction(action)

    def set_document(self, document):
        wallet_changed = self.model.document.wallet != document.wallet
        self.model.set_document(document)
        if self.wallet is not None and wallet_changed:
            self.wallet.refresh()

    def refresh_economy(self):
        if self.wallet is not None:
            self.wallet.refresh()
        last = self.model.rowCount() - 1
        for index, column in enumerate(self.model.document.columns):
            if last >= 0 and column.data_type == "projection" and column.field_key == "cost":
                self.model.dataChanged.emit(
                    self.model.index(0, index), self.model.index(last, index)
                )

    def refresh_references(self, cells):
        self.model.refresh_cells(cells)

    def hideEvent(self, event):
        self.model.flush_owned_edits()
        super().hideEvent(event)

    def _activate_reference(self, index):
        if not index.isValid():
            return
        kind = self.model.column(index).data_type
        if kind == "entity_ref":
            self.pick_reference(index)
        elif kind == "projection":
            self.open_reference(index)

    def pick_reference(self, index):
        if self.references is None:
            return
        row, col = self.model.key(index)
        column = self.model.column(index)
        if column.data_type != "entity_ref":
            return
        value = self.model.document.rows[index.row()].value(col)
        generation = self.model.service.core.generation
        picker = EntityPicker(self.references, column, self.table, current=value)
        point = self.table.viewport().mapToGlobal(self.table.visualRect(index).bottomLeft())
        screen = QApplication.screenAt(point)
        if screen:
            rect = screen.availableGeometry()
            point.setX(min(point.x(), rect.right() - picker.width()))
            point.setY(min(point.y(), rect.bottom() - picker.height()))
        picker.move(point)
        if picker.exec() == picker.DialogCode.Accepted:
            try:
                if generation != self.model.service.core.generation:
                    raise ValueError("Проект изменился; выбор отменён")
                self.model.service.set_cell(
                    self.model.document.id, row, col, picker.chosen_id, expected=value, parsed=True
                )
            except ValueError as error:
                self.model.service.reject_draft(
                    self.model.document.id, row, col, picker.chosen_id, error
                )
                self.error.setText(str(error))
        picker.deleteLater()

    def open_reference(self, index):
        if self.references is None or not index.isValid():
            return
        column = self.model.column(index)
        source = column.id if column.data_type == "entity_ref" else column.source_column_id
        if source is None:
            return
        value = self.model.document.rows[index.row()].value(source)
        info = self.references.info(value)
        if info:
            self.open_entity(info.kind, info.id)
        else:
            self.error.setText("Документ недоступен")

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.matches(QKeySequence.StandardKey.Paste):
                self.paste_selection()
                return True
            index = self.table.currentIndex()
            if index.isValid() and self.model.column(index).data_type in {
                "entity_ref",
                "projection",
            }:
                if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space}:
                    if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                        self.open_reference(index)
                    else:
                        self._activate_reference(index)
                    return True
        if (
            obj is self.table.viewport()
            and event.type() == QEvent.Type.MouseButtonPress
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            index = self.table.indexAt(event.position().toPoint())
            if index.isValid() and self.model.column(index).data_type in {
                "entity_ref",
                "projection",
            }:
                self.open_reference(index)
                return True
        return super().eventFilter(obj, event)

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
        self.model.apply(replace(doc, rows=(*doc.rows, doc.new_row())))
        if doc.columns:
            self.table.setCurrentIndex(self.model.index(len(doc.rows), 0))
            self.table.scrollTo(self.table.currentIndex())

    def remove_row(self):
        doc = self.model.document
        identity = getattr(self, "_context_row_id", None)
        index = (
            next((i for i, row in enumerate(doc.rows) if row.id == identity), -1)
            if identity
            else self.table.currentIndex().row()
        )
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
        kinds = {
            "Текст": "text",
            "Число": "number",
            "Флажок": "bool",
            "Ссылка на документ": "entity_ref",
            "Свойство связанного документа": "projection",
        }
        label, ok = QInputDialog.getItem(self, "Тип", "Тип:", list(kinds), 0, False)
        if ok:
            kind = kinds[label]
            doc = self.model.document
            try:
                column = self._column_definition(name, kind, len(doc.columns))
            except ValueError as error:
                self.error.setText(str(error))
                return
            if column is None:
                return
            self._apply(lambda: replace(doc, columns=(*doc.columns, column)))
            if doc.rows:
                self.table.setCurrentIndex(self.model.index(0, len(doc.columns)))
                self.table.scrollTo(self.table.currentIndex())

    def edit_column(self):
        doc = self.model.document
        identity = getattr(self, "_context_column_id", None)
        index = (
            next((i for i, col in enumerate(doc.columns) if col.id == identity), -1)
            if identity
            else self.table.currentIndex().column()
        )
        if index < 0:
            return
        column = doc.columns[index]
        name, ok = QInputDialog.getText(self, "Колонка", "Название:", text=column.name)
        if not ok or not name.strip():
            return
        labels = {
            "Текст": "text",
            "Число": "number",
            "Флажок": "bool",
            "Ссылка на документ": "entity_ref",
            "Свойство связанного документа": "projection",
        }
        kind_label, ok = QInputDialog.getItem(
            self, "Тип", "Тип:", list(labels), list(labels.values()).index(column.data_type), False
        )
        if not ok:
            return

        def update():
            kind = labels[kind_label]
            changed = (
                replace(column, name=name)
                if kind == column.data_type
                else self._column_definition(name, kind, column.position, column)
            )
            if changed is None:
                return
            # Strict change: incompatible existing values are rejected, never dropped/coerced.
            return replace(
                doc, columns=tuple(changed if c.id == column.id else c for c in doc.columns)
            )

        self._apply(update)

    def _column_definition(self, name, kind, position, old=None):
        metadata = {}
        if kind == "entity_ref":
            if self.references is None:
                raise ValueError("Не подключён каталог документов")
            kinds = {"Карточка": "card", "Карта": "map", "Таблица": "table"}
            label, ok = QInputDialog.getItem(
                self, "Ссылка", "Тип документа:", list(kinds), 0, False
            )
            if not ok:
                return None
            metadata["ref_kind"] = kinds[label]
            if kinds[label] == "card":
                choices = [("Любой тип", None), *self.references.type_options]
                value, ok = QInputDialog.getItem(
                    self, "Ссылка", "Тип карточки:", [label for label, key in choices], 0, False
                )
                if not ok:
                    return None
                metadata["ref_card_type"] = dict(choices)[value]
        if kind == "projection":
            columns = [c for c in self.model.document.columns if c.data_type == "entity_ref"]
            if not columns:
                raise ValueError("Сначала добавьте столбец ссылки")
            choices = {c.name + " · " + c.id[:8]: c for c in columns}
            label, ok = QInputDialog.getItem(
                self, "Свойство", "Столбец ссылки:", list(choices), 0, False
            )
            if not ok:
                return None
            source = choices[label]
            options = dict(
                self.references.field_options
                if source.ref_kind == "card"
                else (("Название", "title"),)
            )
            field, ok = QInputDialog.getItem(
                self, "Свойство", "Поле документа:", list(options), 0, False
            )
            if not ok:
                return None
            metadata.update(source_column_id=source.id, field_key=options[field])
        if old is None:
            return ColumnDefinition(name, kind, position, **metadata)
        if old.key is not None:
            return replace(old, name=name, data_type=kind)
        return ColumnDefinition(name, kind, position, old.id, **metadata)

    def remove_column(self):
        doc = self.model.document
        identity = getattr(self, "_context_column_id", None)
        index = (
            next((i for i, col in enumerate(doc.columns) if col.id == identity), -1)
            if identity
            else self.table.currentIndex().column()
        )
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
            self._context_column_id = self.model.document.columns[index].id
            menu.addAction("Название и тип…", self.edit_column)
            menu.addAction("Удалить столбец…", self.remove_column)
        menu.exec(header.mapToGlobal(point))
        self._context_column_id = None

    def _row_menu(self, point):
        header = self.table.verticalHeader()
        index = header.logicalIndexAt(point)
        menu = QMenu(self)
        menu.addAction("Добавить строку", self.add_row)
        if index >= 0:
            self._context_row_id = self.model.document.rows[index].id
            menu.addAction("Удалить строку…", self.remove_row)
        menu.exec(header.mapToGlobal(point))
        self._context_row_id = None

    def _resolve_conflict(self, identity, mine):
        if self.model.service and identity:
            self.model.flush_owned_edits()
            if self.model.service.resolve_conflict(*identity, mine=mine):
                self.revert_active_editor()
            self.update_draft_notice()

    def update_draft_notice(self):
        service = self.model.service
        rows = {r.id: r for r in self.model.document.rows}
        columns = {c.id: c for c in self.model.document.columns}
        self.conflicts.set_conflicts(
            [
                (
                    key,
                    "Конфликт · " + columns[key[2]].name,
                    service.drafts(key[0]).get(key[1:], conflict.raw),
                    rows[key[1]].value(key[2]),
                )
                for key, conflict in service.conflicts.items()
                if key[0] == self.model.document.id and key[1] in rows and key[2] in columns
            ]
            if service
            else []
        )
        invalid = bool(self.model.drafts)
        self.discard.setVisible(invalid)
        if not invalid:
            self.error.clear()
        else:
            message = next(
                (
                    self.model.service.draft_error(self.model.document.id, row, col)
                    for row, col in self.model.drafts
                    if self.model.service
                    and self.model.service.draft_error(self.model.document.id, row, col)
                ),
                "",
            )
            self.error.setText(
                message or "Ошибочный ввод не сохранён. Другие данные можно сохранять."
            )

    def copy_selection(self):
        indexes = self.table.selectionModel().selectedIndexes()
        if not indexes:
            return
        rows, cols = [i.row() for i in indexes], [i.column() for i in indexes]
        stream = io.StringIO()
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        for y in range(min(rows), max(rows) + 1):
            writer.writerow(
                [
                    self.model.data(
                        self.model.index(y, x),
                        Qt.ItemDataRole.EditRole
                        if self.model.document.columns[x].data_type == "entity_ref"
                        else Qt.ItemDataRole.DisplayRole,
                    )
                    for x in range(min(cols), max(cols) + 1)
                ]
            )
        copy_text(stream.getvalue().rstrip("\n"))

    def paste_selection(self):
        clipboard = QApplication.clipboard()
        data = clipboard.mimeData()
        if self.paste_inventory is not None and data is not None and data.hasFormat(INVENTORY_MIME):
            source = data.data(INVENTORY_MIME)
            self._apply(lambda: self.paste_inventory(decode_inventory_transfer(bytes(source))))
            return
        self._apply(
            lambda: self.model.paste(self.table.currentIndex(), clipboard.text())
        )

    def _apply(self, operation):
        try:
            result = operation()
            if result is not None:
                self.model.apply(result)
            self.error.clear()
        except ValueError as error:
            self.error.setText(str(error))
