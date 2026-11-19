"""Compare one canonical normalized store with a disposable JSON encoding, not two formats."""

import json
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from lodandsy.application.sqlite_project_store import ProjectSnapshot, SQLiteProjectStore
from lodandsy.domain.table_document import ColumnDefinition, RowRecord, TableDocument
from lodandsy.ui.table_widget import TableWidget


def main():
    app = QApplication([])
    start = time.perf_counter()
    columns = tuple(
        ColumnDefinition(f"Column{i}", "number" if i % 2 else "text", i) for i in range(20)
    )
    rows = tuple(
        RowRecord(y, tuple((c.id, y if c.data_type == "number" else f"Value {y}") for c in columns))
        for y in range(5000)
    )
    table = TableDocument("Load", columns=columns, rows=rows)
    result = {
        "rows": 5000,
        "columns": 20,
        "cells": 100000,
        "construct_s": round(time.perf_counter() - start, 3),
    }
    start = time.perf_counter()
    source = json.dumps(asdict(table), ensure_ascii=False)
    result["json_encode_s"] = round(time.perf_counter() - start, 3)
    start = time.perf_counter()
    json.loads(source)
    result["json_parse_s"] = round(time.perf_counter() - start, 3)
    result["json_bytes"] = len(source.encode())
    with tempfile.TemporaryDirectory(prefix="lodandsy-table-") as folder:
        store = SQLiteProjectStore.create(Path(folder) / "world")
        start = time.perf_counter()
        store.save(ProjectSnapshot((), 1, tables=(table,)))
        result["sqlite_save_s"] = round(time.perf_counter() - start, 3)
        start = time.perf_counter()
        assert store.load().tables == (table,)
        result["sqlite_load_validate_s"] = round(time.perf_counter() - start, 3)
        result["sqlite_bytes"] = store.path.stat().st_size
        start = time.perf_counter()
        widget = TableWidget(table)
        widget.resize(1200, 700)
        widget.show()
        app.processEvents()
        canvas = QImage(1200, 700, QImage.Format.Format_RGB32)
        widget.render(canvas)
        result["first_view_s"] = round(time.perf_counter() - start, 3)
        start = time.perf_counter()
        widget.model.setData(widget.model.index(0, 0), "Edited")
        result["single_cell_edit_s"] = round(time.perf_counter() - start, 3)
        widget.close()
        store.close()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
