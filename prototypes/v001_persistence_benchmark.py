"""Measure canonical edits, save stages and catalogue reads on isolated Windows worlds."""

import argparse
import ctypes
import json
import platform
import shutil
import sqlite3
import tempfile
from collections import defaultdict
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path
from statistics import median
from threading import get_ident
from time import perf_counter, sleep
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from lodandsy.application.app_controller import AppController
from lodandsy.application.project_catalogue import ProjectCatalogue
from lodandsy.application.project_controller import ProjectController
from lodandsy.application.project_history import ProjectHistory
from lodandsy.application.sqlite_project_store import ProjectSnapshot, SQLiteProjectStore
from lodandsy.domain import document_payloads
from lodandsy.domain.actor_state import ActorRef, ActorState
from lodandsy.domain.card import Card
from lodandsy.domain.entity import Entity, EntityCollection
from lodandsy.domain.map_document import MapDocument, TokenInstance
from lodandsy.domain.table_document import RowRecord, TableDocument, inventory_columns
from lodandsy.ui.app_shell import AppShell
from prototypes.actors_profile import memory

PROFILES = {
    # Participants, items, maps, placements, inventory rows per participant.
    "small": (12, 24, 3, 48, 8),
    "medium": (60, 120, 6, 360, 16),
    "large": (180, 300, 12, 1080, 32),
}


class Phases:
    def __init__(self):
        self.main = get_ident()
        self.elapsed = defaultdict(float)
        self.calls = defaultdict(int)
        self.worker_finished = None

    @contextmanager
    def measure(self, phase):
        lane = "gui" if get_ident() == self.main else "worker"
        started = perf_counter()
        try:
            yield
        finally:
            self.elapsed[lane, phase] += (perf_counter() - started) * 1000
            self.calls[lane, phase] += 1

    def wrap(self, phase, function):
        def measured(*args, **kwargs):
            with self.measure(phase):
                return function(*args, **kwargs)

        return measured

    def value(self, lane, phase):
        return self.elapsed.get((lane, phase), 0)

    def readings(self):
        return {f"{lane}_{phase}_ms": round(value, 4)
                for (lane, phase), value in self.elapsed.items()}


def io_written():
    counters = (ctypes.c_ulonglong * 6)()
    kernel = ctypes.windll.kernel32
    query = kernel.GetProcessIoCounters
    query.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    if not query(ctypes.c_void_p(-1), ctypes.byref(counters)):
        raise OSError("GetProcessIoCounters failed")
    return counters[4]  # WriteTransferCount, including journal writes.


def workload(profile, asset):
    actor_count, item_count, map_count, token_count, rows_per_actor = profile
    items = tuple(Card(f"Предмет {i}", card_type="item") for i in range(item_count))
    tables, participants, sources = [], [], []
    for i in range(actor_count):
        columns = inventory_columns()
        rows = tuple(
            RowRecord(j, ((columns[0].id, items[(i * 7 + j) % item_count].id),
                          (columns[1].id, 1), (columns[-1].id, False)))
            for j in range(rows_per_actor)
        )
        table = TableDocument(f"Инвентарь {i}", columns=columns, rows=rows)
        actor = ActorState(
            f"Участник {i}", (("hp_current", 18), ("hp_temp", 0)), inventory_id=table.id,
        )
        card = Card(
            f"Карточка {i}", card_type="character",
            values=(("hp_max", 24), ("player", i < 4)), actors=(actor,),
            default_actor_id=actor.id if i < 4 else None,
        )
        participants.append(card)
        tables.append(table)
        sources.append((card, actor))
    tokens = []
    for i in range(token_count):
        card, actor = sources[i if i < actor_count else i % 4]
        tokens.append(TokenInstance(
            card.id, 64 + i % 24 * 64, 64 + i // 24 % 15 * 64, actor_id=actor.id,
        ))
    maps = tuple(
        MapDocument(f"Карта {i}", asset.id, tokens=tuple(tokens[i::map_count]))
        for i in range(map_count)
    )
    roots = (*participants, *items, *maps)
    envelopes = tuple(
        Entity(doc.id, "map" if isinstance(doc, MapDocument) else "card", doc.title, position=i)
        for i, doc in enumerate(roots)
    ) + tuple(
        Entity(table.id, "table", table.title, card.id)
        for table, card in zip(tables, participants, strict=True)
    )
    return ProjectSnapshot((*participants, *items), 1, (asset,), maps, tuple(tables), envelopes)


def instrument(stack, phases, controller, project):
    validate = phases.wrap("validate", document_payloads.validate_project)
    stack.enter_context(patch.object(document_payloads, "validate_project", validate))
    stack.enter_context(patch.object(controller.core.entities, "validator", validate))
    stack.enter_context(patch.object(
        controller.core, "prepare", phases.wrap("reconcile", controller.core.prepare),
    ))
    stack.enter_context(patch.object(
        project.saver, "_snapshot", phases.wrap("snapshot", project.saver._snapshot),
    ))
    atomic = EntityCollection.atomic

    def atomic_step(function, *args):
        lane = "gui" if get_ident() == phases.main else "worker"
        validated = phases.value(lane, "validate")
        elapsed = phases.value(lane, "atomic")
        with phases.measure("atomic"):
            result = function(*args)
        phases.elapsed[lane, "atomic_without_validation"] += max(
            0, phases.value(lane, "atomic") - elapsed
            - (phases.value(lane, "validate") - validated),
        )
        return result

    @contextmanager
    def observed_atomic(collection):
        nested = atomic(collection)
        value = atomic_step(nested.__enter__)
        try:
            yield value
        except BaseException as error:
            if not atomic_step(nested.__exit__, type(error), error, error.__traceback__):
                raise
        else:
            atomic_step(nested.__exit__, None, None, None)

    stack.enter_context(patch.object(EntityCollection, "atomic", observed_atomic))
    read = phases.wrap("read_snapshot", SQLiteProjectStore._read_snapshot)
    stack.enter_context(patch.object(SQLiteProjectStore, "_read_snapshot", staticmethod(read)))
    connect = sqlite3.connect

    class TimedCursor(sqlite3.Cursor):
        execute = phases.wrap("sqlite", sqlite3.Cursor.execute)
        executemany = phases.wrap("sqlite", sqlite3.Cursor.executemany)
        fetchone = phases.wrap("sqlite", sqlite3.Cursor.fetchone)
        fetchall = phases.wrap("sqlite", sqlite3.Cursor.fetchall)
        __next__ = phases.wrap("sqlite", sqlite3.Cursor.__next__)

    class TimedConnection(sqlite3.Connection):
        __exit__ = phases.wrap("sqlite", sqlite3.Connection.__exit__)

        def execute(self, *args, **kwargs):
            return self.cursor(TimedCursor).execute(*args, **kwargs)

        def executemany(self, *args, **kwargs):
            return self.cursor(TimedCursor).executemany(*args, **kwargs)

    def timed_connect(*args, **kwargs):
        with phases.measure("sqlite"):
            return connect(*args, **kwargs, factory=TimedConnection)

    stack.enter_context(patch.object(sqlite3, "connect", timed_connect))

    def persist(snapshot):
        with phases.measure("write"):
            project.store.save(snapshot)
        phases.worker_finished = perf_counter()

    stack.enter_context(patch.object(project.saver, "_persist", persist))


def catalogue_reads(root, catalogue, store, phases):
    managed = catalogue.root
    for i in range(3):
        world = managed / f"Копия {i}"
        world.mkdir(parents=True)
        shutil.copy2(store.path, world / store.path.name)
        shutil.copytree(store.root / "assets", world / "assets")
    phases.calls.clear()
    assert len(catalogue.entries(())) == 3
    assert phases.calls["gui", "read_snapshot"] == 3
    started = perf_counter()
    assert all(not entry["error"] for entry in catalogue.entries(()))
    listing = (perf_counter() - started) * 1000
    # Reproduce the selected-world path: open validates, then activation loads again.
    phases.calls.clear()
    candidate = managed / "Копия 0"
    started = perf_counter()
    with closing(SQLiteProjectStore.open(candidate)) as opened:
        open_ms = (perf_counter() - started) * 1000
        started = perf_counter()
        opened.load()
        reload_ms = (perf_counter() - started) * 1000
    assert phases.calls["gui", "read_snapshot"] == 2
    return {"three_world_listing_ms": round(listing, 3), "one_world_open_ms": round(open_ms, 3),
            "second_load_ms": round(reload_ms, 3), "selected_world_full_reads": 2}


def benchmark(profile, sample_count, root):
    app = QApplication.instance() or QApplication([])
    window = AppShell()
    window.resize(1000, 700)
    controller = AppController(window)
    catalogue = ProjectCatalogue(lambda: root / "Documents")
    history = ProjectHistory(QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat))
    project = ProjectController(controller, history, catalogue)
    empty_memory = memory()
    try:
        with closing(SQLiteProjectStore.create(root / "world")) as store:
            source = root / "map.png"
            image = QImage(1600, 1024, QImage.Format.Format_RGB32)
            image.fill(0xFF507050)
            assert image.save(str(source))
            snapshot = workload(profile, store.import_asset(source))
            store.save(snapshot)
        project.open_project(root / "world")
        window.show()
        document = snapshot.maps[0]
        map_view = controller.maps.open_map(document.id).widget().view
        deadline = perf_counter() + 30
        while map_view._background is None and perf_counter() < deadline:
            app.processEvents()
            sleep(0.005)
        assert map_view._background is not None
        loaded_memory = memory()
        card = snapshot.cards[0]
        table = snapshot.tables[0]
        actor_ref = ActorRef(card.id, card.actors[0].id)
        token = document.tokens[0]
        operations = {
            "card_field": lambda n: controller.cards_service.update_card_fields(
                card.id, {"summary": f"Поле {n}"},
            ),
            "actor_hp": lambda n: controller.cards_service.update_actor(
                actor_ref, {"hp_current": 12 + n},
            ),
            "item_quantity": lambda n: controller.tables_service.set_cell(
                table.id, table.rows[0].id, table.columns[1].id, 2 + n, parsed=True,
            ),
            "token_move": lambda n: controller.maps_service.move_token(
                document.id, token.id, 200 + n, 200,
            ),
        }
        phases = Phases()
        records = defaultdict(list)
        acks = []

        def acknowledge(revision):
            assert revision == project.saver.revision and phases.worker_finished is not None
            acks.append((perf_counter() - phases.worker_finished) * 1000)

        project.saver.saved.connect(acknowledge)
        with ExitStack() as stack:
            instrument(stack, phases, controller, project)
            for i in range(sample_count + 1):
                for name, edit in operations.items():
                    app.processEvents()
                    phases.elapsed.clear()
                    phases.calls.clear()
                    previous_io = io_written()
                    previous_revision = project.saver.revision
                    with phases.measure("edit"):
                        edit(i % 2)
                    assert project.saver.revision == previous_revision + 1
                    started = perf_counter()
                    assert project.saver.save(), project.saver.last_error
                    save_ms = (perf_counter() - started) * 1000
                    assert project.saver.saved_revision == project.saver.revision and acks
                    sample = phases.readings()
                    sample |= {"worker_to_ack_ms": round(acks.pop(), 4),
                               "save_wall_ms": round(save_ms, 4),
                               "write_bytes": io_written() - previous_io}
                    if i:
                        records[name].append(sample)
            catalogue_data = catalogue_reads(root, catalogue, project.store, phases)
        return {
            "platform": platform.platform(), "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version, "qt_platform": app.platformName(),
            "profile": dict(zip(
                ("actors", "items", "maps", "tokens", "rows_per_actor"), profile, strict=True,
            )),
            "samples_after_warmup": sample_count,
            "db_bytes": project.store.path.stat().st_size,
            "empty_memory_mib": empty_memory, "loaded_memory_mib": loaded_memory,
            "final_memory_mib": memory(),
            "median": {name: {
                key: round(median(record[key] for record in samples), 4)
                for key in samples[0]
            } for name, samples in records.items()},
            "samples": records, "catalogue": catalogue_data,
        }
    finally:
        project.saver.shutdown()
        controller.shutdown_features()
        if project.store is not None:
            project.store.close()
        window.close_guard = None
        window.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=PROFILES, required=True)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--report", type=Path, required=True)
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="lodandsy-audit-benchmark-") as temporary:
        result = benchmark(PROFILES[options.profile], options.samples, Path(temporary))
    options.report.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
