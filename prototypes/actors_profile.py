"""Real Qt application workload; isolated world/catalogue, no user projects."""

import argparse
import ctypes
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path


def memory():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
            (key, ctypes.c_size_t)
            for key in (
                "peak",
                "working",
                "pool_peak",
                "pool",
                "nonpage_peak",
                "nonpage",
                "page",
                "page_peak",
            )
        ]

    result = Counters()
    result.cb = ctypes.sizeof(result)
    query = ctypes.windll.psapi.GetProcessMemoryInfo
    query.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
    if query(ctypes.c_void_p(-1), ctypes.byref(result), result.cb):
        return {"peak_mib": result.peak / 1024**2, "working_mib": result.working / 1024**2}
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path)
    parser.add_argument("--mode", choices=("shared", "independent"), default="shared")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.checkout:
        sys.path.insert(0, str(args.checkout.resolve()))
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    from lodandsy.application.app_controller import AppController
    from lodandsy.application.project_controller import ProjectController
    from lodandsy.application.project_history import ProjectHistory
    from lodandsy.domain.card_schema import FIELD_DEFINITIONS
    from lodandsy.ui.app_shell import AppShell

    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="lodandsy-actors-profile-") as temporary:
        root = Path(temporary)
        window = AppShell()
        controller = AppController(window)
        project = ProjectController(
            controller,
            ProjectHistory(QSettings(str(root / "user.ini"), QSettings.Format.IniFormat)),
        )
        window.show()

        def wait(predicate):
            end = time.perf_counter() + 60
            while not predicate():
                if time.perf_counter() >= end:
                    raise RuntimeError("Timed out waiting for production map")
                app.processEvents()
                time.sleep(0.005)

        try:
            project.create_project(root / "Мир")
            image = QImage(1200, 800, QImage.Format.Format_RGB32)
            image.fill(0xFF202020)
            source = root / "source.png"
            assert image.save(str(source))
            asset = project.store.import_asset(source)
            project.assets[asset.id] = asset
            modern = "hp_max" in FIELD_DEFINITIONS
            kwargs = {"player": True} if modern and args.mode == "shared" else {}
            card = controller.create_card("Participant", card_type="character", **kwargs)
            controller.cards_service.update_card_fields(card.id, {"hp_max" if modern else "hp": 20})
            document = controller.maps_service.create_map("Map", asset.id)
            start = time.perf_counter()
            with controller.core.transaction():
                for i in range(args.count):
                    controller.maps_service.add_token(
                        document.id, card.id, 20 + (i % 40) * 27, 20 + (i // 40) * 27
                    )
            setup = time.perf_counter() - start
            widget = controller.maps.open_map(document.id).widget()
            wait(lambda: widget.view._background is not None)
            app.processEvents()
            assert len(widget.view._tokens) == args.count
            assert project.save_current()
            old_items = tuple(widget.view._tokens)
            event_count = []
            if modern:
                from lodandsy.domain.actor_state import ActorRef

                token = controller.maps_service.get_map(document.id).tokens[0]
                reference = ActorRef(card.id, token.actor_id)
                controller.cards_service.actor_changed.connect(
                    lambda *event: event_count.append(event)
                )
                controller.cards_service.update_actor(reference, {"hp_current": 20})
            samples = []
            for i in range(20):
                start = time.perf_counter()
                if modern:
                    controller.cards_service.update_actor(
                        reference, {"hp_current": 19 if i % 2 else 20}
                    )
                else:
                    controller.cards_service.update_card_fields(
                        card.id, {"hp": 19 if i % 2 else 20}
                    )
                app.processEvents()
                samples.append((time.perf_counter() - start) * 1000)
            assert all(a is b for a, b in zip(old_items, widget.view._tokens))
            start = time.perf_counter()
            assert project.save_current()
            save_ms = (time.perf_counter() - start) * 1000
            start = time.perf_counter()
            snapshot = project.store.load()
            load_ms = (time.perf_counter() - start) * 1000
            path = project.store.root
            # Production project replacement closes the old writer and document views.
            project.create_project(root / "Other", preserve_current=False)
            start = time.perf_counter()
            project.open_project(path)
            widget = controller.maps.open_map(document.id).widget()
            wait(lambda: widget.view._background is not None)
            reopen_ms = (time.perf_counter() - start) * 1000
            actors = sum(len(getattr(c, "actors", ())) for c in snapshot.cards)
            result = {
                "mode": args.mode,
                "modern": modern,
                "placements": args.count,
                "actors": actors,
                "tables": len(snapshot.tables),
                "setup_seconds": setup,
                "edit_render_p50_ms": statistics.median(samples),
                "edit_render_p95_ms": sorted(samples)[18],
                "actor_events_for_20_edits": len(event_count),
                "token_items_reused": True,
                "save_ms": save_ms,
                "load_snapshot_ms": load_ms,
                "reopen_map_ready_ms": reopen_ms,
                "memory": memory(),
                "platform": app.platformName(),
                "same_background_pixels": 960000,
                "note": "Native programmatic render/events; not physical smoothness or SLA",
            }
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result))
        finally:
            window.close_guard = None
            controller.maps.shutdown()
            project.saver.shutdown()
            if project.store:
                project.store.close()
            window.close()
            app.processEvents()


if __name__ == "__main__":
    main()
