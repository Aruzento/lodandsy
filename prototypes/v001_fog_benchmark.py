"""Measure preview, paint and completion on the actual Windows Qt Viewer."""

import argparse
import importlib
import json
import math
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent, QPainterPathStroker
from PySide6.QtWidgets import QApplication

from build_support.windows_smoke import wait
from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.ui.app_shell import AppShell


def elapsed(start):
    return (perf_counter_ns() - start) / 1e6


def distribution(values):
    values = sorted(values)
    return {"median_ms": median(values), "p95_ms": values[math.ceil(0.95 * len(values)) - 1]}


def send(view, kind, x, y):
    viewport = view.viewport()
    point = view.viewportTransform().map(QPointF(x, y))
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    start = perf_counter_ns()
    QApplication.sendEvent(viewport, QMouseEvent(
        kind, point, QPointF(viewport.mapToGlobal(point.toPoint())),
        none if kind == QEvent.Type.MouseMove else left,
        none if kind == QEvent.Type.MouseButtonRelease else left, Qt.KeyboardModifier.NoModifier,
    ))
    return elapsed(start)


def measure(qapp, app, maps, viewer, points):
    view, tools = viewer.view, viewer.fog_tools
    samples = {key: [] for key in ("move", "path", "stroker", "paint", "compile")}
    errors = []
    fog_ui = importlib.import_module("lodandsy.ui.fog_tools")
    geometry = importlib.import_module("lodandsy.application.fog_geometry")
    map_ui = importlib.import_module("lodandsy.application.maps_controller")
    path_name = "brush_stroke_path" if hasattr(fog_ui, "brush_stroke_path") else "stroke_path"
    original_path = getattr(fog_ui, path_name)
    original_compile = map_ui.state_path
    original_error = app.maps._error

    def timed(operation, bucket):
        def call(*args, **kwargs):
            start = perf_counter_ns()
            try:
                return operation(*args, **kwargs)
            finally:
                bucket.append(elapsed(start))
        return call

    class Stroker(QPainterPathStroker):
        def createStroke(self, path):
            return timed(super().createStroke, samples["stroker"])(path)

    geometry.QPainterPathStroker = Stroker
    setattr(fog_ui, path_name, timed(original_path, samples["path"]))
    map_ui.state_path = timed(original_compile, samples["compile"])
    app.maps._error = errors.append
    try:
        tools.set_mode("hide")
        tools.size.setValue(12)
        send(view, QEvent.Type.MouseButtonPress, *points[0])
        for index, point in enumerate(points[1:], 1):
            samples["move"].append(send(view, QEvent.Type.MouseMove, *point))
            if index % 12 == 0:
                start = perf_counter_ns()
                view.viewport().repaint()
                samples["paint"].append(elapsed(start))
        kept = len(tools.points)
        paths_before_release = len(samples["path"])
        path_time = sum(samples["path"])
        stroker_time = sum(samples["stroker"])
        release = send(view, QEvent.Type.MouseButtonRelease, *points[-1])
        complete = app.maps_service.undo_stack(maps.id).canUndo()
        if complete:
            app.maps_service.undo_stack(maps.id).undo()
        qapp.processEvents()
        return {
            "input_points": len(points), "kept_before_release": kept, "committed": complete,
            "errors": errors,
            "move": distribution(samples["move"]),
            "last_64_moves": distribution(samples["move"][-64:]),
            "preview_path": distribution(samples["path"][:paths_before_release]),
            "path_total_ms": path_time, "stroker_total_ms": stroker_time,
            "preview_path_other_ms": max(0, path_time - stroker_time),
            "viewport_repaint": distribution(samples["paint"]),
            "release_ms": release, "compile_ms": samples["compile"][0] if complete else 0,
        }
    finally:
        geometry.QPainterPathStroker = QPainterPathStroker
        setattr(fog_ui, path_name, original_path)
        map_ui.state_path = original_compile
        app.maps._error = original_error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    qapp = QApplication([])
    window = AppShell()
    app = AppController(window)
    projects = ProjectController(app)
    window.show()
    with TemporaryDirectory(prefix="lodandsy-fog-r2-") as directory:
        root = Path(directory)
        try:
            projects.create_project(root / "world")
            image = QImage(1600, 900, QImage.Format.Format_RGB32)
            image.fill(0xFF51606A)
            image.save(str(path := root / "map.png"))
            app.maps.import_map(path, "Проверка кисти")
            wait(qapp, lambda: not app.maps.importing)
            maps = next(iter(app.maps_service.maps.values()))
            viewer = app.maps.open_map(maps.id).widget()
            wait(qapp, viewer.token_add.isEnabled)
            wait(qapp, lambda: bool(app.maps.tiles.images))
            results = {}
            for count in (96, 480, 720):
                # Frequent crossings in a stable, fully visible part of the map.
                points = [(800 + 110 * math.sin(i * 0.08), 450 + 70 * math.sin(i * 0.136))
                          for i in range(count)]
                results[str(count)] = measure(qapp, app, maps, viewer, points)
            args.report.write_text(json.dumps(results, indent=2), encoding="utf-8")
        finally:
            app.shutdown_features()
            projects.saver.shutdown()
            if projects.store:
                projects.store.close()
            window.close_guard = None
            window.close()


if __name__ == "__main__":
    main()
