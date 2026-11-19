import math
import re
from dataclasses import dataclass, field, replace
from uuid import uuid4

from lodandsy.domain.module_values import validate_id, validate_title


@dataclass(frozen=True, slots=True)
class ColumnDefinition:
    name: str
    data_type: str = "text"
    position: int = 0
    id: str = field(default_factory=lambda: str(uuid4()))
    key: str | None = None
    ref_kind: str | None = None
    ref_card_type: str | None = None
    source_column_id: str | None = None
    field_key: str | None = None
    integer: bool = False
    minimum: float | None = None
    maximum: float | None = None
    required: bool = False
    default: object = None

    def __post_init__(self):
        validate_id(self.id)
        object.__setattr__(self, "name", validate_title(self.name))
        if self.data_type not in {"text", "number", "bool", "entity_ref", "projection"}:
            raise ValueError("Unsupported column type")
        if type(self.position) is not int or self.position < 0:
            raise ValueError("Invalid column position")
        for value in (self.key, self.ref_card_type, self.field_key):
            if value is not None and (
                not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value)
            ):
                raise ValueError("Invalid stable column/field key")
        if type(self.integer) is not bool or type(self.required) is not bool:
            raise ValueError("Invalid column constraint")
        for value in (self.minimum, self.maximum):
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                raise ValueError("Invalid number bound")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Invalid number range")
        if self.data_type != "number" and (
            self.integer or self.minimum is not None or self.maximum is not None
        ):
            raise ValueError("Number constraints require number column")
        if self.data_type == "entity_ref":
            if self.ref_kind not in {None, "card", "map", "table"} or (
                self.ref_card_type and self.ref_kind != "card"
            ):
                raise ValueError("Invalid reference constraint")
        elif self.ref_kind is not None or self.ref_card_type is not None:
            raise ValueError("Reference constraint requires entity_ref")
        if self.data_type == "projection":
            validate_id(self.source_column_id)
            if (
                self.source_column_id == self.id
                or self.field_key is None
                or self.default is not None
            ):
                raise ValueError("Invalid read-only projection")
        elif self.source_column_id is not None or self.field_key is not None:
            raise ValueError("Projection metadata requires projection column")
        if self.default is not None:
            self.validate(self.default)

    def validate(self, value):
        if self.data_type == "projection":
            raise ValueError("Вычисляемый столбец доступен только для чтения")
        validate_value(value, self.data_type)
        if value is None:
            if self.required:
                raise ValueError("Обязательное значение не заполнено")
            return
        if self.data_type == "number" and (
            self.integer
            and type(value) is not int
            or self.minimum is not None
            and value < self.minimum
            or self.maximum is not None
            and value > self.maximum
        ):
            raise ValueError("Число не соответствует ограничениям столбца")


@dataclass(frozen=True, slots=True)
class RowRecord:
    position: int = 0
    cells: tuple = ()  # Immutable (column_id, scalar) pairs; absence differs from empty text.
    id: str = field(default_factory=lambda: str(uuid4()))

    _validated_columns: tuple | None = field(default=None, init=False, compare=False, repr=False)

    def __post_init__(self):
        validate_id(self.id)
        if type(self.position) is not int or self.position < 0 or not isinstance(self.cells, tuple):
            raise ValueError("Invalid row")
        keys = set()
        for cell in self.cells:
            if not isinstance(cell, tuple) or len(cell) != 2:
                raise ValueError("Invalid cell")
            validate_id(cell[0])
            if cell[0] in keys:
                raise ValueError("Duplicate cell column ID")
            keys.add(cell[0])
        object.__setattr__(self, "cells", tuple(sorted(self.cells)))

    def value(self, column_id):
        return next((value for key, value in self.cells if key == column_id), None)


def validate_value(value, data_type):
    if value is None:
        return
    if data_type == "entity_ref":
        validate_id(value)
        return
    valid = (
        (
            data_type == "text"
            and isinstance(value, str)
            and "\0" not in value
            and len(value.encode("utf-8")) <= 65536
        )
        or (
            data_type == "number"
            and type(value) in {int, float}
            and abs(value) <= 1e15
            and math.isfinite(value)
        )
        or (data_type == "bool" and type(value) is bool)
    )
    if not valid:
        raise ValueError(f"Значение не соответствует типу {data_type}")


def parse_cell(text, data_type):
    if data_type == "text":
        value = text
    elif not str(text).strip():
        value = None
    elif data_type == "bool":
        if str(text).casefold() not in {"true", "false", "1", "0", "да", "нет"}:
            raise ValueError("Введите true/false или 1/0")
        value = str(text).casefold() in {"true", "1", "да"}
    elif data_type == "entity_ref":
        value = str(text).strip()
        validate_id(value)
    elif data_type == "projection":
        raise ValueError("Вычисляемый столбец доступен только для чтения")
    else:
        try:
            value = float(text)
        except ValueError, TypeError:
            raise ValueError("Введите конечное число") from None
        if value.is_integer():
            value = int(value)
    validate_value(value, data_type)
    return value


@dataclass(frozen=True, slots=True)
class TableDocument:
    title: str
    id: str = field(default_factory=lambda: str(uuid4()))
    columns: tuple[ColumnDefinition, ...] = field(
        default_factory=lambda: (ColumnDefinition("Столбец 1"),)
    )
    rows: tuple[RowRecord, ...] = ()

    def __post_init__(self):
        validate_id(self.id)
        object.__setattr__(self, "title", validate_title(self.title))
        for values, kind, limit in [
            (self.columns, ColumnDefinition, 64),
            (self.rows, RowRecord, 50000),
        ]:
            if (
                not isinstance(values, tuple)
                or len(values) > limit
                or not all(isinstance(v, kind) for v in values)
            ):
                raise ValueError("Invalid table structure or budget exceeded")
            if len({v.id for v in values}) != len(values):
                raise ValueError("Duplicate table ID")
            if tuple(v.position for v in values) != tuple(range(len(values))):
                raise ValueError("Invalid table order")
        columns = {c.id: c for c in self.columns}
        keys = [c.key for c in self.columns if c.key is not None]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate stable column key")
        for column in self.columns:
            if (
                column.data_type == "projection"
                and (source := columns.get(column.source_column_id)) is not None
                and source.data_type != "entity_ref"
            ):
                raise ValueError("Projection source must be entity_ref")
        signature = self.columns
        for row in self.rows:
            if row._validated_columns == signature:
                continue
            for key, value in row.cells:
                if key not in columns:
                    raise ValueError("Cell refers to unknown column")
                columns[key].validate(value)
            for column in self.columns:
                if column.required and row.value(column.id) is None:
                    raise ValueError("Обязательное значение не заполнено")
            # Derived proof cache: cells and column definitions are immutable validated scalars.
            object.__setattr__(row, "_validated_columns", signature)

    def with_cell(self, row_id, column_id, value):
        column = next((c for c in self.columns if c.id == column_id), None)
        if column is None or not any(r.id == row_id for r in self.rows):
            raise ValueError("Unknown cell ID")
        column.validate(value)
        rows = tuple(
            replace(
                r,
                cells=tuple((key, v) for key, v in r.cells if key != column_id)
                + ((column_id, value),),
            )
            if r.id == row_id
            else r
            for r in self.rows
        )
        return replace(self, rows=rows)

    def new_row(self):
        return RowRecord(
            len(self.rows), tuple((c.id, c.default) for c in self.columns if c.default is not None)
        )


def display_value(value):
    return (
        ""
        if value is None
        else ("true" if value is True else "false" if value is False else str(value))
    )


@dataclass(frozen=True, slots=True)
class TablePayload:
    columns: tuple
    rows: tuple
    version: int = field(default=3, init=False)


def inventory_columns():
    item = ColumnDefinition(
        "Предмет", "entity_ref", key="item", ref_kind="card", ref_card_type="item"
    )
    return (
        item,
        ColumnDefinition(
            "Количество",
            "number",
            1,
            key="quantity",
            integer=True,
            minimum=1,
            required=True,
            default=1,
        ),
        ColumnDefinition(
            "Описание",
            "projection",
            2,
            key="description",
            source_column_id=item.id,
            field_key="description_preview",
        ),
        ColumnDefinition(
            "Стоимость", "projection", 3, key="cost", source_column_id=item.id, field_key="cost"
        ),
    )
