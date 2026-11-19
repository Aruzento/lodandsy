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
from lodandsy.domain.card import Portrait
from lodandsy.domain.map_document import MapGrid, TokenInstance
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
    phase = ["setup"]
    phase_gaps = {}
    last = [time.perf_counter()]

    def tick():
        now = time.perf_counter()
        gaps.append((now - last[0]) * 1000)
        phase_gaps.setdefault(phase[0], []).append((now - last[0]) * 1000)
        last[0] = now
        peak[0] = max(peak[0], process.memory_info().rss)
        for child in process.children(recursive=True):
            try:
                peak[1] = max(peak[1], child.memory_info().rss)
            except psutil.NoSuchProcess:
                pass

    def set_phase(name):
        tick()  # Attribute elapsed work to the preceding phase before changing its label.
        phase[0] = name

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
            time.sleep(0.001)

    try:
        with (
            tempfile.TemporaryDirectory(prefix="lodandsy-map-runtime-") as temporary,
            ExitStack() as cleanup,
        ):
            cleanup.callback(lambda: project.store.close() if project.store else None)
            cleanup.callback(controller.modules.shutdown)
            cleanup.callback(controller.card_images.shutdown)
            cleanup.callback(project.saver.shutdown)
            project.create_project(Path(temporary) / "world")
            set_phase("import")
            start = time.perf_counter()
            controller.modules.import_map(args.source, "Measured raster")
            wait(lambda: not controller.modules.importing)
            document = next(iter(controller.modules.session.maps.values()))
            widget = controller.modules.open_map(document.id).widget()
            wait(lambda: "Колесо" in widget.message.text())
            import_seconds = time.perf_counter() - start
            set_phase("scene_setup")
            second = controller.modules.session.create_map("Second view", document.asset_id)
            other = controller.modules.open_map(second.id).widget()
            wait(lambda: "Колесо" in other.message.text())
            if args.tokens:
                token_source = Path(temporary) / "token.png"
                token_image = QImage(32, 32, QImage.Format.Format_RGB32)
                token_image.fill(0xFFAB8040)
                token_image.save(str(token_source))
                asset = project.store.import_asset(token_source)
                project.assets[asset.id] = asset
                columns = 40
                rows = (args.tokens + columns - 1) // columns
                card = controller.create_card("Shared Card", card_type="character")
                controller.session.update_card(card.id, portrait=Portrait(asset.id))
                tokens = tuple(
                    TokenInstance(
                        card.id,
                        (i % columns + 0.5) / columns * widget.view.map_width,
                        (i // columns + 0.5) / rows * widget.view.map_height,
                        cells_w=1,
                        cells_h=1,
                    )
                    for i in range(args.tokens)
                )
                controller.modules.session.edit_map(
                    document.id, tokens=tokens, grid=MapGrid(True, 100)
                )
            for doc in (document, second):
                layers = [
                    controller.modules.session.add_layer(doc.id, f"Layer {i}") for i in range(2)
                ]
                for i in range(15):
                    controller.modules.session.add_object(
                        doc.id,
                        layers[i % 2].id,
                        asset.id if args.tokens else doc.asset_id,
                        100 + i * 300,
                        200 + i * 200,
                        160,
                        120,
                    )
            set_phase("renderer")
            samples = []
            tile_counts = []
            canvas = QImage(1000, 700, QImage.Format.Format_RGB32)
            for index in range(80):
                view = widget.view if index % 2 else other.view
                view.resetTransform()
                view.scale((0.1, 0.5, 1, 2)[index % 4], (0.1, 0.5, 1, 2)[index % 4])
                view.centerOn((index * 137) % view.map_width, (index * 83) % view.map_height)
                start = time.perf_counter()
                painter = QPainter(canvas)
                view.render(painter)
                painter.end()
                samples.append((time.perf_counter() - start) * 1000)
                tile_counts.append(view._background.last_tile_count)
                app.processEvents()
                time.sleep(0.01)
            wait(lambda: not controller.modules.tiles.pending)
            drag = []
            if args.tokens:
                set_phase("drag")
                token = controller.modules.session.get_map(document.id).tokens[0]
                for i in range(30):
                    start = time.perf_counter()
                    controller.modules.session.move_token(
                        document.id, token.id, 100 + i * 20, 200 + i * 20
                    )
                    app.processEvents()
                    drag.append((time.perf_counter() - start) * 1000)
            set_phase("save")
            start = time.perf_counter()
            assert project.save_current()
            save_ms = (time.perf_counter() - start) * 1000
            set_phase("backup")
            start = time.perf_counter()
            backup_path = Path(temporary) / "backup.lodbackup"
            project.store.backup(backup_path)
            backup_ms = (time.perf_counter() - start) * 1000
            app.processEvents()
            set_phase("reopen")
            project._save_ui_state()
            controller.window_manager.close_window(f"map:{document.id}")
            start = time.perf_counter()
            reopened = controller.modules.open_map(document.id).widget()
            wait(lambda: "Колесо" in reopened.message.text())
            result = {
                "source": args.source.name,
                "source_bytes": args.source.stat().st_size,
                "width": widget.view.map_width,
                "height": widget.view.map_height,
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
                "placed_objects": 30,
                "layers_per_map": 2,
                "save_ms": save_ms,
                "backup_block_ms": backup_ms,
                "backup_bytes": backup_path.stat().st_size,
                "drag_p50_ms": sorted(drag)[len(drag) // 2] if drag else None,
                "drag_p95_ms": sorted(drag)[int(len(drag) * 0.95)] if drag else None,
                "phase_tick_gaps_max_ms": {key: max(values) for key, values in phase_gaps.items()},
                "tile_disk_bytes": sum(
                    p.stat().st_size
                    for p in (project.store.root / ".lodandsy-cache").rglob("*")
                    if p.is_file()
                ),
                "ram_gib": round(psutil.virtual_memory().total / 1024**3, 2),
                "dpi": [s.logicalDotsPerInch() for s in app.screens()],
                "logical_cpu": os.cpu_count(),
                "platform": app.platformName(),
                "manual_smoothness": "not evaluated by this automated measurement",
            }
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
