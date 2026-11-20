"""Table commands, canonical projections and session drafts, independent of feature UI."""

from dataclasses import dataclass, replace
from types import MappingProxyType
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from lodandsy.application.edit_conflict import ConcurrentEditError, EditConflict
from lodandsy.application.entity_session import EntitySession
from lodandsy.domain.table_document import TableDocument, TablePayload, display_value, parse_cell

_UNSET = object()


@dataclass(slots=True)
class CellEdit:
    table_id: str
    row_id: str
    column_id: str
    base: object
    raw: str
    committed_text: str
    initial_draft: object = None
    draft_version: object = None
    initial_status: tuple = ()


@dataclass(frozen=True, slots=True)
class TableChange:
    cells: frozenset = frozenset()
    structure: bool = False
    title: bool = False


class TablesService(QObject):
    table_changed = Signal(str, object)
    table_deleted = Signal(str)
    draft_changed = Signal(str, object)
    pending_changed = Signal()
    projections_changed = Signal(str, object)

    def __init__(self, core=None, parent=None, *, references=None):
        super().__init__(parent)
        self.core = core if core is not None else EntitySession(parent=self)
        self._drafts = {}
        self._draft_snapshots = {}
        self.references = references
        self._edits = {}
        self._orphans = {}
        self._errors = {}
        self.conflicts = {}
        self._draft_bases = {}
        self._draft_versions = {}
        self._lookups = {}
        self._ref_rows = {}
        self._table_edges = {}
        if references is not None:
            references.changed.connect(self._references_changed)
        self.core.entity_changed.connect(self._entity_changed)
        self.core.entities_deleted.connect(self._deleted)
        self.core.replaced.connect(self.reset)

    @property
    def tables(self):
        return MappingProxyType(
            {
                e.id: self.get_table(e.id)
                for e in self.core.entities.summaries()
                if e.kind == "table"
            }
        )

    def get_table(self, key):
        if self.core.entities.get(key).kind != "table":
            raise ValueError("Ожидается таблица")
        return self.core.entities.project(
            key, lambda e, p: TableDocument(e.title, e.id, p.columns, p.rows)
        )

    def create_table(self, title, parent_id=None, *, columns=None):
        document = (
            TableDocument(title) if columns is None else TableDocument(title, columns=columns)
        )
        with self.core.transaction():
            self.core.entities.create(
                "table",
                document.title,
                TablePayload(document.columns, document.rows),
                parent_id,
                id=document.id,
            )
            self.core.after_commit(lambda: self.core.entity_created.emit(document.id))
            self.core.after_commit(
                lambda: self.table_changed.emit(document.id, TableChange(structure=True))
            )
            self.core.mark_changed()
        return document

    def edit_table(self, key, **changes):
        if changes.keys() - {"title", "columns", "rows"}:
            raise ValueError("Неподдерживаемые поля таблицы")
        return self.update_table(replace(self.get_table(key), **changes))

    def update_table(self, document, *, expected=None):
        if not isinstance(document, TableDocument):
            raise ValueError("Ожидается валидированная таблица")
        before = self.get_table(document.id)
        if expected is not None and before != expected:
            raise ValueError("Таблица изменилась в другом представлении; повторите команду")
        if before == document:
            return before
        structural = before.columns != document.columns or tuple(
            r.id for r in before.rows
        ) != tuple(r.id for r in document.rows)
        cells = (
            frozenset()
            if structural
            else frozenset(
                (new.id, col.id)
                for old, new in zip(before.rows, document.rows)
                if old is not new and old != new
                for col in document.columns
                if old.value(col.id) != new.value(col.id)
            )
        )
        change = TableChange(cells, structural, before.title != document.title)
        self._validate_references(before, document)
        with self.core.transaction():
            self.core.entities.update(document.id, title=document.title)
            self.core.entities.put_payload(
                document.id, TablePayload(document.columns, document.rows)
            )
            self.core.entities.project(document.id, lambda e, p: document)
            self._lookups.pop(document.id, None)
            self.track_references(document.id, change)
            self.core.after_commit(lambda: self.table_changed.emit(document.id, change))
            self.core.mark_changed()
        return document

    def drafts(self, key):
        self.get_table(key)
        return self._drafts.setdefault(key, {})

    @property
    def draft_count(self):
        return sum(map(len, self._drafts.values())) + len(self._orphans)

    @property
    def draft_table_ids(self):
        return tuple(key for key, values in self._drafts.items() if values)

    def notify_drafts(self, key, *, edit=None, touched=()):
        current = self.drafts(key)
        before = self._draft_snapshots.get(key, {})
        changed = frozenset(
            cell for cell in current.keys() | before.keys() if current.get(cell) != before.get(cell)
        )
        for cell in changed | set(touched):
            identity = key, *cell
            version = self._draft_versions[identity] = object()
            if edit is not None and (edit.row_id, edit.column_id) == cell:
                edit.draft_version = version
        for identity in self.conflicts.keys() | self._draft_bases.keys():
            if identity[0] == key and identity[1:] not in current:
                self.conflicts.pop(identity, None)
                self._draft_bases.pop(identity, None)
        errors = self._errors.get(key, {})
        for cell in tuple(errors):
            if cell not in current:
                errors.pop(cell)
        self._draft_snapshots[key] = dict(current)
        self.draft_changed.emit(key, changed)

    def discard_drafts(self, key):
        self.drafts(key).clear()
        self._errors.pop(key, None)
        for owner, edit in tuple(self._edits.items()):
            if edit.table_id == key:
                self._edits.pop(owner)
        self.notify_drafts(key)
        self.pending_changed.emit()

    def reset(self):
        self._drafts.clear()
        self._draft_snapshots.clear()
        self._edits.clear()
        self._orphans.clear()
        self._errors.clear()
        self.conflicts.clear()
        self._draft_bases.clear()
        self._draft_versions.clear()
        self._lookups.clear()
        self._ref_rows.clear()
        self._table_edges.clear()

    def _entity_changed(self, key, fields):
        if self.core.entities.get(key).kind == "table":
            self.table_changed.emit(key, TableChange(title="title" in fields))

    def _deleted(self, keys):
        for key in keys:
            for identity in (
                self.conflicts.keys() | self._draft_bases.keys() | self._draft_versions.keys()
            ):
                if identity[0] == key:
                    self.conflicts.pop(identity, None)
                    self._draft_bases.pop(identity, None)
                    self._draft_versions.pop(identity, None)
            self._drafts.pop(key, None)
            self._draft_snapshots.pop(key, None)
            self._lookups.pop(key, None)
            self._remove_edges(key)
            for owner, edit in tuple(self._edits.items()):
                if edit.table_id == key and edit.raw != edit.committed_text:
                    self._orphans[(key, edit.row_id, edit.column_id)] = (
                        edit.raw,
                        "Таблица удалена во время ввода",
                    )
                if edit.table_id == key:
                    self._edits.pop(owner, None)
            self.table_deleted.emit(key)

    def _cell(self, key, row_id, column_id):
        document = self.get_table(key)
        cached = self._lookups.get(key)
        if cached is None or cached[0] is not document:
            cached = (
                document,
                {r.id: r for r in document.rows},
                {c.id: c for c in document.columns},
            )
            self._lookups[key] = cached
        row, column = cached[1].get(row_id), cached[2].get(column_id)
        if row is None or column is None:
            raise ValueError("Строка или столбец удалены во время ввода")
        return document, row, column

    def _validate_target(self, column, value):
        if column.data_type == "entity_ref" and value is not None:
            if (
                self.references is None
                or self.references.resolve(value, column.ref_kind, column.ref_card_type) is None
            ):
                raise ValueError("Ссылка не соответствует допустимому типу или документ недоступен")

    def _validate_references(self, before, after):
        references = [column for column in after.columns if column.data_type == "entity_ref"]
        if not references:
            return
        old_rows = {r.id: r for r in before.rows}
        old_cols = {c.id: c for c in before.columns}
        for row in after.rows:
            old = old_rows.get(row.id)
            if old is row and before.columns == after.columns:
                continue
            for column in references:
                previous = old_cols.get(column.id)
                value = row.value(column.id)
                if (
                    old is None
                    or previous is None
                    or previous.data_type != "entity_ref"
                    or (previous.ref_kind, previous.ref_card_type)
                    != (column.ref_kind, column.ref_card_type)
                    or old.value(column.id) != value
                ):
                    self._validate_target(column, value)

    def set_cell(self, key, row_id, column_id, raw, *, expected=_UNSET, parsed=False):
        document, row, column = self._cell(key, row_id, column_id)
        value = raw if parsed else parse_cell(raw, column.data_type)
        column.validate(value)
        if (
            expected is not _UNSET
            and row.value(column_id) != expected
            and value != row.value(column_id)
        ):
            raise ConcurrentEditError(
                "Ячейка изменена в другом представлении. Текущее значение: "
                + display_value(row.value(column_id)),
                expected,
                row.value(column_id),
            )
        self._validate_target(column, value)
        return self.update_table(document.with_cell(row_id, column_id, value))

    def begin_edit(self, key, row_id, column_id):
        document, row, column = self._cell(key, row_id, column_id)
        raw = self.drafts(key).get((row_id, column_id), display_value(row.value(column_id)))
        owner = str(uuid4())
        identity = key, row_id, column_id
        conflict = self.conflicts.get(identity)
        self._edits[owner] = CellEdit(
            key,
            row_id,
            column_id,
            self._draft_bases.get((key, row_id, column_id), row.value(column_id)),
            raw,
            raw,
            self.drafts(key).get((row_id, column_id)),
            self._draft_versions.get(identity),
            (
                self._errors.get(key, {}).get((row_id, column_id)),
                self._draft_bases.get(identity, row.value(column_id)),
                replace(conflict) if conflict else None,
            ),
        )
        return owner

    def edit_text(self, owner, text):
        edit = self._edits.get(owner)
        if edit is not None:
            edit.raw = text
            self.pending_changed.emit()

    def edit_value(self, owner):
        return self._edits[owner].raw

    def has_edit(self, owner):
        return owner in self._edits

    @property
    def pending_count(self):
        return sum(edit.raw != edit.committed_text for edit in self._edits.values())

    @property
    def orphan_drafts(self):
        return tuple((key, raw, error) for key, (raw, error) in self._orphans.items())

    def discard_orphans(self):
        self._orphans.clear()
        self.pending_changed.emit()

    def reject_draft(self, key, row_id, column_id, raw, error, *, edit=None):
        try:
            self._cell(key, row_id, column_id)
        except ValueError:
            self._orphans[(key, row_id, column_id)] = (raw, str(error))
            self.pending_changed.emit()
            return
        if isinstance(error, ConcurrentEditError):
            identity = key, row_id, column_id
            self.conflicts[identity] = EditConflict(raw, error.base, error.observed)
            self._draft_bases.setdefault(identity, error.base)
        self.drafts(key)[(row_id, column_id)] = raw
        self._errors.setdefault(key, {})[(row_id, column_id)] = str(error)
        self.notify_drafts(key, edit=edit, touched=((row_id, column_id),))

    def draft_error(self, key, row_id, column_id):
        return self._errors.get(key, {}).get((row_id, column_id), "")

    def commit_edit(self, owner, *, finish=False):
        edit = self._edits.get(owner)
        if edit is None:
            return False
        if edit.raw == edit.committed_text and edit.initial_draft is None:
            if finish:
                self._edits.pop(owner, None)
            return True
        identity = edit.table_id, edit.row_id, edit.column_id
        try:
            if identity in self.conflicts:
                self.conflicts[identity].raw = edit.raw
                raise ValueError(
                    "Конфликт: выберите «Использовать сохранённое» или «Применить мой вариант»"
                )
            self.set_cell(edit.table_id, edit.row_id, edit.column_id, edit.raw, expected=edit.base)
            _, row, _ = self._cell(edit.table_id, edit.row_id, edit.column_id)
            edit.base = row.value(edit.column_id)
            edit.committed_text = edit.raw
            edit.initial_draft = None
            self.drafts(edit.table_id).pop((edit.row_id, edit.column_id), None)
            self._errors.get(edit.table_id, {}).pop((edit.row_id, edit.column_id), None)
            self.notify_drafts(edit.table_id, edit=edit, touched=((edit.row_id, edit.column_id),))
            success = True
        except ValueError as error:
            self._draft_bases.setdefault(identity, edit.base)
            self.reject_draft(
                edit.table_id, edit.row_id, edit.column_id, edit.raw, error, edit=edit
            )
            success = False
        if finish:
            self._edits.pop(owner, None)
        self.pending_changed.emit()
        return success

    def resolve_conflict(self, key, row_id, column_id, *, mine=False):
        identity = key, row_id, column_id
        conflict = self.conflicts.get(identity)
        if mine:
            if conflict is None:
                return False
            _, row, _ = self._cell(*identity)
            current = row.value(column_id)
            if current != conflict.observed:
                conflict.observed = current
                self.reject_draft(
                    *identity,
                    self.drafts(key)[(row_id, column_id)],
                    "Сохранённое значение снова изменилось: " + display_value(current),
                )
                return False
            try:
                self.set_cell(*identity, self.drafts(key)[(row_id, column_id)], expected=current)
            except ValueError as error:
                self.reject_draft(*identity, self.drafts(key)[(row_id, column_id)], error)
                return False
        for owner, edit in tuple(self._edits.items()):
            if (edit.table_id, edit.row_id, edit.column_id) == identity:
                self._edits.pop(owner)
        self.drafts(key).pop((row_id, column_id), None)
        self.conflicts.pop(identity, None)
        self._draft_bases.pop(identity, None)
        self._errors.get(key, {}).pop((row_id, column_id), None)
        self.notify_drafts(key, touched=((row_id, column_id),))
        self.pending_changed.emit()
        return True

    def cancel_edit(self, owner):
        edit = self._edits.pop(owner, None)
        if edit is None:
            return
        identity = edit.table_id, edit.row_id, edit.column_id
        if self._draft_versions.get(identity) is not edit.draft_version:
            self.pending_changed.emit()
            return
        try:
            values = self.drafts(edit.table_id)
            if edit.initial_draft is None:
                values.pop((edit.row_id, edit.column_id), None)
            else:
                values[(edit.row_id, edit.column_id)] = edit.initial_draft
                error, base, conflict = edit.initial_status
                self._draft_bases[identity] = base
                for state, key, value in (
                    (self._errors.setdefault(edit.table_id, {}), identity[1:], error),
                    (self.conflicts, identity, conflict),
                ):
                    if value is None:
                        state.pop(key, None)
                    else:
                        state[key] = value
            self.notify_drafts(edit.table_id, touched=(identity[1:],))
        except ValueError:
            pass
        self.pending_changed.emit()

    def flush_edits(self):
        for owner in tuple(self._edits):
            self.commit_edit(owner)

    def cell_projection(self, document, row, column):
        if column.data_type == "entity_ref":
            value = row.value(column.id)
            if value is None:
                return None, "", None
            info = (
                self.references.resolve(value, column.ref_kind, column.ref_card_type)
                if self.references
                else None
            )
            return (
                (info.title, "", info)
                if info
                else (
                    None,
                    "Предмет недоступен"
                    if column.ref_card_type == "item"
                    else "Документ недоступен",
                    None,
                )
            )
        if column.data_type == "projection":
            source = next((c for c in document.columns if c.id == column.source_column_id), None)
            if source is None:
                return None, "Источник проекции удалён", None
            value = row.value(source.id)
            if value is None:
                return None, "", None
            info = (
                self.references.resolve(value, source.ref_kind, source.ref_card_type)
                if self.references
                else None
            )
            if info is None:
                return (
                    None,
                    "Предмет недоступен"
                    if source.ref_card_type == "item"
                    else "Документ недоступен",
                    None,
                )
            if column.field_key not in {name for name, value in info.fields}:
                return None, "Поле проекции недоступно", info
            return info.value(column.field_key), "", info
        return row.value(column.id), "", None

    def _remove_edges(self, key):
        for cell, target in self._table_edges.pop(key, {}).items():
            edges = self._ref_rows.get(target)
            if edges is not None:
                edges.discard((key, *cell))
                if not edges:
                    self._ref_rows.pop(target, None)

    def track_references(self, key, change=None):
        document = self.get_table(key)
        sources = [col for col in document.columns if col.data_type == "entity_ref"]
        if not sources:
            self._remove_edges(key)
            return
        if change is None or change.structure:
            self._remove_edges(key)
            rows = document.rows
        else:
            ids = {row for row, col in change.cells}
            rows = (row for row in document.rows if row.id in ids)
        edges = self._table_edges.setdefault(key, {})
        for row in rows:
            for col in sources:
                cell = (row.id, col.id)
                old = edges.pop(cell, None)
                if old is not None:
                    previous = self._ref_rows.get(old)
                    if previous is not None:
                        previous.discard((key, *cell))
                        if not previous:
                            self._ref_rows.pop(old, None)
                value = row.value(col.id)
                if value is not None:
                    edges[cell] = value
                    self._ref_rows.setdefault(value, set()).add((key, *cell))

    def _references_changed(self, keys, fields):
        by_table = {}
        for key in keys:
            for table, row, source in self._ref_rows.get(key, ()):
                columns = self.get_table(table).columns
                cells = by_table.setdefault(table, set())
                cells.add((row, source))
                cells.update(
                    (row, c.id)
                    for c in columns
                    if c.data_type == "projection" and c.source_column_id == source
                )
        for table, cells in by_table.items():
            self.projections_changed.emit(table, frozenset(cells))
