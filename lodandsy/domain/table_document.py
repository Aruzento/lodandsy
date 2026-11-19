import math
from dataclasses import dataclass, field, replace
from random import SystemRandom
from uuid import uuid4

from lodandsy.domain.module_values import validate_id, validate_title


@dataclass(frozen=True, slots=True)
class ColumnDefinition:
    name: str
    data_type: str = "text"
    position: int = 0
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self):
        validate_id(self.id)
        object.__setattr__(self, "name", validate_title(self.name))
        if self.data_type not in {"text", "number", "bool"}:
            raise ValueError("Unsupported column type")
        if type(self.position) is not int or self.position < 0:
            raise ValueError("Invalid column position")


@dataclass(frozen=True, slots=True)
class RowRecord:
    position: int = 0
    cells: tuple = ()  # Immutable (column_id, scalar) pairs; absence differs from empty text.
    id: str = field(default_factory=lambda: str(uuid4()))

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
class RandomTable:
    title: str
    id: str = field(default_factory=lambda: str(uuid4()))
    columns: tuple[ColumnDefinition, ...] = field(
        default_factory=lambda: (ColumnDefinition("Вариант"),)
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
        for row in self.rows:
            for key, value in row.cells:
                if key not in columns:
                    raise ValueError("Cell refers to unknown column")
                validate_value(value, columns[key].data_type)

    def with_cell(self, row_id, column_id, value):
        column = next((c for c in self.columns if c.id == column_id), None)
        if column is None or not any(r.id == row_id for r in self.rows):
            raise ValueError("Unknown cell ID")
        validate_value(value, column.data_type)
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

    def choose(self, rng=None):
        choices = [
            r
            for r in self.rows
            if any(
                v is not None and (not isinstance(v, str) or bool(v.strip())) for _, v in r.cells
            )
        ]
        if not choices:
            raise ValueError("Добавьте хотя бы одну непустую строку")
        row = (rng or SystemRandom()).choice(choices)
        return row.position + 1, row

    def row_text(self, row):
        return " · ".join(f"{c.name}: {display_value(row.value(c.id))}" for c in self.columns)


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
    version: int = field(default=2, init=False)
