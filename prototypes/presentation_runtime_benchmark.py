"""Measure real large-map GM/player/fog with production owners; psutil is profiling-only."""

import argparse
import gc
import json
import tempfile
import time
from pathlib import Path

import psutil
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from lodandsy.application.app_controller import AppController
from lodandsy.application.fog_geometry import stroke_path
from lodandsy.application.project_controller import ProjectController
from lodandsy.application.project_history import ProjectHistory
from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.domain.map_document import TokenInstance
from lodandsy.domain.map_fog import FogRegion, FogState
from lodandsy.ui.app_shell import AppShell


def percentile(values, p):
    return round(sorted(values)[min(len(values) - 1, int(len(values) * p))], 3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    app = QApplication([])
    window = AppShell()
    owner = AppController(window)
    process = psutil.Process()
    rss = [0, 0]
    gaps = []
    last = [time.perf_counter()]

    def tick():
        now = time.perf_counter()
        gaps.append((now - last[0]) * 1000)
        last[0] = now
        rss[0] = max(rss[0], process.memory_info().rss)
        for child in process.children(recursive=True):
            try:
                rss[1] = max(rss[1], child.memory_info().rss)
            except psutil.NoSuchProcess:
                pass

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(16)

    def wait(predicate, seconds=180):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() > deadline:
                raise TimeoutError("Map benchmark timed out")
            app.processEvents()
            time.sleep(0.005)

    with tempfile.TemporaryDirectory(prefix="lodandsy-player7-") as temporary:
        root = Path(temporary)
        history = ProjectHistory(QSettings(str(root / "user.ini"), QSettings.Format.IniFormat))
        project = ProjectController(owner, history)
        try:
            window.resize(1440, 960)
            window.show()
            project.create_project(root / "Мир7")
            started = time.perf_counter()
            owner.maps.import_map(args.source, "Большая карта")
            wait(lambda: not owner.maps.importing)
            document = next(iter(owner.maps_service.maps.values()))
            viewer = owner.maps.open_map(document.id).widget()
            wait(lambda: viewer.view._background is not None)
            import_s = time.perf_counter() - started
            card = owner.create_card("Shared Token")
            tokens = tuple(
                TokenInstance(
                    card.id,
                    (i % 40 + 0.5) / 40 * viewer.view.map_width,
                    (i // 40 + 0.5) / 25 * viewer.view.map_height,
                )
                for i in range(1000)
            )
            owner.maps_service.edit_map(document.id, tokens=tokens)
            for i in range(30):
                owner.maps_service.add_object(
                    document.id,
                    document.layers[0].id,
                    document.asset_id,
                    100 + i * 300,
                    100 + i * 200,
                    128,
                    128,
                )
            regions = tuple(
                FogRegion(
                    (
                        (
                            (i % 8 * 2000, i // 8 * 1200),
                            (i % 8 * 2000 + 1600, i // 8 * 1200),
                            (i % 8 * 2000 + 1600, i // 8 * 1200 + 900),
                            (i % 8 * 2000, i // 8 * 1200 + 900),
                        ),
                    )
                )
                for i in range(64)
            )
            owner.maps_service.edit_map(document.id, fog=FogState(regions))
            player = owner.maps.open_presentation(document.id)
            player.resize(1280, 720)
            wait(lambda: player.view._display_ready)
            assert player.view._background.tiles is viewer.view._background.tiles
            assert player.view._fog_state is owner.maps_service.get_map(document.id).fog
            renders, drag, fog = [], [], []
            for i in range(60):
                started = time.perf_counter()
                viewer.view.restore_camera(
                    dict(x=(i % 10) / 10, y=(i % 7) / 7, zoom=(0.08, 0.2, 0.5)[i % 3])
                )
                for view in (viewer.view, player.view):
                    image = QImage(view.viewport().size(), QImage.Format.Format_RGB32)
                    painter = QPainter(image)
                    view.render(painter)
                    painter.end()
                app.processEvents()
                renders.append((time.perf_counter() - started) * 1000)
            wait(lambda: not owner.maps.tiles.pending)
            revision = project.saver.revision
            for i in range(60):
                started = time.perf_counter()
                owner.maps._transient(
                    document.id, "token", tokens[0].id, 100 + i * 5, 200 + i * 5, viewer.view
                )
                app.processEvents()
                drag.append((time.perf_counter() - started) * 1000)
            assert project.saver.revision == revision
            for i in range(12):
                started = time.perf_counter()
                path = stroke_path(
                    [(1000 + j * 20, 500 + i * 300 + (j % 5) * 20) for j in range(64)], 120
                )
                owner.maps_service.edit_fog(document.id, path, erase=bool(i % 2))
                app.processEvents()
                fog.append((time.perf_counter() - started) * 1000)
            started = time.perf_counter()
            assert project.save_current()
            save_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            project.store.backup(root / "copy.lodbackup")
            backup_ms = (time.perf_counter() - started) * 1000
            before_close = process.memory_info().rss
            owner.maps.close_presentation(document.id)
            app.processEvents()
            gc.collect()
            after_close = process.memory_info().rss
            tile_cache_bytes = owner.maps.tiles.bytes
            pixel_count = viewer.view.map_width * viewer.view.map_height
            old_root = project.store.root
            other = SQLiteProjectStore.create(root / "Другой")
            other.close()
            project.open_project(root / "Другой")
            started = time.perf_counter()
            project.open_project(old_root)
            reopened = owner.maps.open_map(document.id).widget()
            wait(lambda: reopened.view._background is not None)
            reopen_s = time.perf_counter() - started
            result = dict(
                source=args.source.name,
                pixels=pixel_count,
                platform=app.platformName(),
                dpi=[s.logicalDotsPerInch() for s in app.screens()],
                import_s=round(import_s, 3),
                reopen_s=round(reopen_s, 3),
                tokens=1000,
                objects=30,
                fog_regions=64,
                shared_tile_cache=True,
                tile_cache_bytes=tile_cache_bytes,
                tile_cache_budget_mib=64,
                gui_peak_rss_mib=round(rss[0] / 2**20, 2),
                worker_peak_rss_mib=round(rss[1] / 2**20, 2),
                two_view_render_p50_ms=percentile(renders, 0.5),
                two_view_render_p95_ms=percentile(renders, 0.95),
                transient_p50_ms=percentile(drag, 0.5),
                transient_p95_ms=percentile(drag, 0.95),
                fog_gesture_p50_ms=percentile(fog, 0.5),
                fog_gesture_p95_ms=percentile(fog, 0.95),
                save_ms=round(save_ms, 3),
                backup_block_ms=round(backup_ms, 3),
                player_close_rss_before_mib=round(before_close / 2**20, 2),
                player_close_rss_after_mib=round(after_close / 2**20, 2),
                max_gui_tick_gap_ms=round(max(gaps), 3),
                physical_smoothness="not evaluated",
            )
            args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result))
        finally:
            timer.stop()
            window.close_guard = None
            owner.shutdown_features()
            project.saver.shutdown()
            if project.store:
                project.store.close()
            window.close()


if __name__ == "__main__":
    main()
