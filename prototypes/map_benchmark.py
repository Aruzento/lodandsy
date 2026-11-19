"""Disposable M1 image/scene measurement, not a product SLA or demo world."""

import json
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.domain.map_document import MapPin
from lodandsy.ui.app_shell import AppShell


def main():
    app = QApplication([])
    window = AppShell()
    controller = AppController(window)
    project = ProjectController(controller)
    window.show()
    with tempfile.TemporaryDirectory(prefix="lodandsy-map-benchmark-") as temporary:
        root = Path(temporary)
        project.create_project(root / "world")
        source = root / "16mp.png"
        image = QImage(4000, 4000, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.darkCyan)
        image.save(str(source))
        ticks, last = [], [time.perf_counter()]
        timer = QTimer()
        timer.setInterval(10)
        def tick():
            now = time.perf_counter()
            ticks.append((now - last[0]) * 1000)
            last[0] = now
        timer.timeout.connect(tick)
        timer.start()
        start = time.perf_counter()
        controller.modules.import_map(source, "16MP")
        while controller.modules.importing:
            app.processEvents()
            time.sleep(.001)
        elapsed = (time.perf_counter() - start) * 1000
        timer.stop()
        document = next(iter(controller.modules.session.maps.values()))
        widget = controller.modules.open_map(document.id).widget()
        pins = tuple(MapPin(str(i), (i % 100) / 100, (i // 100) / 100) for i in range(1000))
        start = time.perf_counter()
        widget.view.set_pins(pins, set())
        scene_ms = (time.perf_counter() - start) * 1000
        result = {"image_pixels": 16_000_000, "file_bytes": source.stat().st_size,
                  "import_ms": round(elapsed, 2), "gui_ticks": len(ticks),
                  "largest_tick_gap_ms": round(max(ticks, default=0), 2),
                  "scene_pins": 1000, "scene_refresh_ms": round(scene_ms, 2),
                  "tile_cache_bytes": controller.modules.tiles.bytes}
        print(json.dumps(result))
        project.saver.shutdown()
        controller.modules.shutdown()
        project.store.close()
        window.close_guard = None
        window.close()


if __name__ == "__main__":
    main()
