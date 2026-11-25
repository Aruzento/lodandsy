"""Same-process production paint comparison, not a physical input latency SLA."""

import ctypes
import json
import statistics
import time
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QPoint, QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from lodandsy.domain.card import Card
from lodandsy.domain.map_document import MapDocument, MapGrid, MapShape, TokenInstance
from lodandsy.ui.map_widget import MapView


def memory():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t)
            for name in (
                "peak_working_set",
                "working_set",
                "peak_paged",
                "paged",
                "peak_nonpaged",
                "nonpaged",
                "pagefile",
                "peak_pagefile",
            )
        ]

    value = Counters()
    value.cb = ctypes.sizeof(value)
    get_process = ctypes.windll.kernel32.GetCurrentProcess
    get_process.restype = ctypes.c_void_p
    query = ctypes.windll.psapi.GetProcessMemoryInfo
    query.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
    assert query(get_process(), ctypes.byref(value), value.cb)
    return {"working_set_bytes": value.working_set, "process_peak_bytes": value.peak_working_set}


def main():
    app = QApplication([])
    view = MapView()
    view.resize(1280, 800)
    view.show()
    card = Card("Benchmark")
    tokens = tuple(
        TokenInstance(card.id, 300 + (i % 40) * 500, 300 + (i // 40) * 400) for i in range(1000)
    )
    doc = MapDocument("Benchmark", str(uuid4()), tokens=tokens, grid=MapGrid(feet_per_cell=5))
    view.map_width, view.map_height = 21600, 10800
    view.set_annotations(doc, lambda key: card, None, {}, lambda root, path: QImage())
    view.fitInView(QRectF(0, 0, 21600, 10800))
    app.processEvents()
    image = QImage(view.viewport().size(), QImage.Format.Format_ARGB32)

    def run():
        samples = []
        for i in range(85):
            start = time.perf_counter()
            painter = QPainter(image)
            view.viewport().render(painter, QPoint())
            painter.end()
            if i >= 5:
                samples.append((time.perf_counter() - start) * 1000)
        return {
            "mean_ms": statistics.mean(samples),
            "p95_ms": sorted(samples)[int(0.95 * len(samples)) - 1],
            "samples": len(samples),
            **memory(),
        }

    baseline = run()
    view.measurement = (tokens[0].id, (300, 300), (1800, 1500))
    arrow_only = run()
    view.vector_shapes = tuple(
        MapShape("circle", ((100, 0),), x=300 + (i % 40) * 500, y=300 + (i // 40) * 400)
        for i in range(1000)
    )
    view.measurement = (tokens[0].id, (300, 300), (1800, 1500))
    enabled = run()
    result = {
        "method": (
            "QWidget production viewport render; same process, 1000 tokens; image-free world "
            "21600x10800; 5 warmup+80 samples; cumulative Windows process peak; "
            "not disk/decode or physical input latency"
        ),
        "platform": app.platformName(),
        "baseline_overlay_disabled": baseline,
        "m5_arrow_only": arrow_only,
        "m5_1000_shapes_and_arrow": enabled,
    }
    output = Path("docs/validation/2026-11-25-map-m5/performance.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
    view.close()


if __name__ == "__main__":
    main()
