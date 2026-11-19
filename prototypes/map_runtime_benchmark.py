"""Production Map import/reopen/visible-tiles measurement on a supplied image."""
import argparse
import json
import os
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

import psutil
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.domain.map_document import MapGrid, MapToken
from lodandsy.ui.app_shell import AppShell


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--tokens", type=int, default=0)
    args = parser.parse_args()
    app = QApplication([])
    window = AppShell()
    controller = AppController(window)
    project = ProjectController(controller)
    window.resize(1400, 900)
    window.show()
    process = psutil.Process()
    peak = [0, 0]
    gaps = []
    last = [time.perf_counter()]
    def tick():
        now = time.perf_counter()
        gaps.append((now - last[0]) * 1000)
        last[0] = now
        peak[0] = max(peak[0], process.memory_info().rss)
        for child in process.children(recursive=True):
            try:
                peak[1] = max(peak[1], child.memory_info().rss)
            except psutil.NoSuchProcess:
                pass
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(tick)
    timer.start()
    def wait(predicate):
        deadline = time.monotonic() + 120
        while not predicate():
            if time.monotonic() > deadline:
                raise RuntimeError("Production benchmark timed out")
            app.processEvents()
            time.sleep(.001)
    try:
        with (tempfile.TemporaryDirectory(prefix="lodandsy-map-runtime-") as temporary,
              ExitStack() as cleanup):
            cleanup.callback(lambda: project.store.close() if project.store else None)
            cleanup.callback(controller.modules.shutdown)
            cleanup.callback(controller.card_images.shutdown)
            cleanup.callback(project.saver.shutdown)
            project.create_project(Path(temporary) / "world")
            start = time.perf_counter()
            controller.modules.import_map(args.source, "Measured raster")
            wait(lambda: not controller.modules.importing)
            document = next(iter(controller.modules.session.maps.values()))
            widget = controller.modules.open_map(document.id).widget()
            wait(lambda: "Колесо" in widget.message.text())
            import_seconds = time.perf_counter() - start
            second = controller.modules.session.create_map("Second view", document.asset_id)
            other = controller.modules.open_map(second.id).widget()
            wait(lambda: "Колесо" in other.message.text())
            if args.tokens:
                token_source = Path(temporary) / "token.png"
                token_image = QImage(32, 32, QImage.Format.Format_RGB32)
                token_image.fill(0xffab8040)
                token_image.save(str(token_source))
                asset = project.store.import_asset(token_source)
                project.assets[asset.id] = asset
                columns = 40
                rows = (args.tokens + columns - 1) // columns
                tokens = tuple(MapToken(f"Token {i}", asset.id,
                    (i % columns + .5) / columns * widget.view.map_width,
                    (i // columns + .5) / rows * widget.view.map_height,
                    width=100, height=100) for i in range(args.tokens))
                controller.modules.session.edit_map(document.id, tokens=tokens,
                    grid=MapGrid(True, 100))
            samples = []
            tile_counts = []
            canvas = QImage(1000, 700, QImage.Format.Format_RGB32)
            for index in range(80):
                view = widget.view if index % 2 else other.view
                view.resetTransform()
                view.scale((.1, .5, 1, 2)[index % 4], (.1, .5, 1, 2)[index % 4])
                view.centerOn((index * 137) % view.map_width, (index * 83) % view.map_height)
                start = time.perf_counter()
                painter = QPainter(canvas)
                view.render(painter)
                painter.end()
                samples.append((time.perf_counter() - start) * 1000)
                tile_counts.append(view._background.last_tile_count)
                app.processEvents()
                time.sleep(.01)
            wait(lambda: not controller.modules.tiles.pending)
            assert project.save_current()
            project._save_ui_state()
            controller.window_manager.close_window(f"map:{document.id}")
            start = time.perf_counter()
            reopened = controller.modules.open_map(document.id).widget()
            wait(lambda: "Колесо" in reopened.message.text())
            result = {"source": args.source.name, "source_bytes": args.source.stat().st_size,
                      "width": widget.view.map_width, "height": widget.view.map_height,
                      "import_and_open_s": round(import_seconds, 3),
                      "cached_reopen_s": round(time.perf_counter() - start, 3),
                      "gui_peak_rss_mib": round(peak[0] / 1024**2, 2),
                      "decoder_peak_rss_mib": round(peak[1] / 1024**2, 2),
                      "pan_zoom_render_p50_ms": round(sorted(samples)[40], 2),
                      "pan_zoom_render_p95_ms": round(sorted(samples)[76], 2),
                      "max_gui_tick_gap_ms": round(max(gaps), 2),
                      "tile_cache_bytes": controller.modules.tiles.bytes,
                      "max_visible_tiles": max(tile_counts),
                      "token_count": args.tokens,
                      "logical_cpu": os.cpu_count(), "platform": app.platformName(),
                      "manual_smoothness": "not evaluated by this automated measurement"}
            args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result))
    finally:
        timer.stop()
        window.close_guard = None
        controller.modules.shutdown()
        controller.card_images.shutdown()
        project.saver.shutdown()
        if project.store:
            project.store.close()
        window.close()


if __name__ == "__main__":
    main()
