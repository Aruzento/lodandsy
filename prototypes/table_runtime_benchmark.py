"""Measured source UI + application + snapshot pipeline; no alternate storage format."""

import argparse
import json
import os
import platform
import tempfile
import time
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.domain.table_document import ColumnDefinition, RowRecord, TableDocument
from lodandsy.ui.app_shell import AppShell


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    app = QApplication([])
    window = AppShell()
    controller = AppController(window)
    project = ProjectController(controller)
    output = {
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "logical_cpu": os.cpu_count(),
        "workloads": [],
    }
    try:
        with (
            tempfile.TemporaryDirectory(prefix="lodandsy-table-runtime-") as folder,
            ExitStack() as cleanup,
        ):
            cleanup.callback(lambda: project.store.close() if project.store else None)
            cleanup.callback(project.saver.wait_current)
            project.create_project(Path(folder) / "world")
            for count, ncols in [(100, 5), (5000, 20)]:
                columns = tuple(
                    ColumnDefinition(f"Column{i}", "number" if i % 2 else "text", i)
                    for i in range(ncols)
                )
                table = TableDocument(
                    "Load",
                    columns=columns,
                    rows=tuple(
                        RowRecord(
                            y,
                            tuple(
                                (c.id, y if c.data_type == "number" else f"Value {y}")
                                for c in columns
                            ),
                        )
                        for y in range(count)
                    ),
                )
                controller.cards_service.entities.create(
                    "table",
                    table.title,
                    __import__(
                        "lodandsy.domain.document_payloads", fromlist=["module_payload"]
                    ).module_payload(table),
                    id=table.id,
                )
                widget = controller.tables.open_table(table.id).widget()
                window.resize(1200, 800)
                window.show()
                app.processEvents()
                resets = []
                ranges = []
                widget.model.modelReset.connect(lambda: resets.append(1))
                widget.model.dataChanged.connect(
                    lambda a, b, *rest: ranges.append(
                        (b.row() - a.row() + 1) * (b.column() - a.column() + 1)
                    )
                )
                gaps = []
                last = [time.perf_counter()]

                def tick():
                    now = time.perf_counter()
                    gaps.append((now - last[0]) * 1000)
                    last[0] = now

                timer = QTimer()
                timer.setInterval(5)
                timer.timeout.connect(tick)
                timer.start()
                times = []
                for i in range(30):
                    start = time.perf_counter()
                    assert widget.model.setData(widget.model.index(i % count, 0), f"Edit {i}")
                    times.append((time.perf_counter() - start) * 1000)
                    app.processEvents()
                current = controller.tables_service.get_table(table.id)
                cold = tuple(replace(row) for row in current.rows)
                start = time.perf_counter()
                replace(current, rows=cold)
                validation = (time.perf_counter() - start) * 1000
                start = time.perf_counter()
                assert project.save_current()
                save = (time.perf_counter() - start) * 1000
                app.processEvents()
                start = time.perf_counter()
                project.store.load()
                load = (time.perf_counter() - start) * 1000
                app.processEvents()
                timer.stop()
                output["workloads"].append(
                    dict(
                        cells=count * ncols,
                        edit_p50_ms=sorted(times)[15],
                        edit_p95_ms=sorted(times)[28],
                        edit_max_ms=max(times),
                        series_ms=sum(times),
                        full_validation_ms=validation,
                        save_ms=save,
                        reopen_ms=load,
                        db_bytes=project.store.path.stat().st_size,
                        model_resets=len(resets),
                        changed_range_max_cells=max(ranges),
                        tick_gap_max_ms=max(gaps, default=0),
                    )
                )
            args.report.write_text(json.dumps(output, indent=2), encoding="utf-8")
            print(json.dumps(output))
    finally:
        window.close_guard = None
        controller.shutdown_features()
        project.saver.shutdown()
        if project.store:
            project.store.close()
        window.close()


if __name__ == "__main__":
    main()
