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
from math import ceil
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
        self.counts = defaultdict(int)
        self.reconciling = False
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
                for (lane, phase), value in self.elapsed.items()} | dict(self.counts)

    def reset(self):
        self.elapsed.clear()
        self.calls.clear()
        self.counts.clear()
        for key in (
            "validated_aggregates", "reconciled_contexts", "full_validations",
            "decoded_snapshots", "decoded_module_batches", "changed_sql_rows",
        ):
            self.counts[key] = 0


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
    original_validate = document_payloads.validate_project
    prepare = controller.core.prepare
    effective = controller.cards_service.effective

    def validate(collection, previous=None):
        if get_ident() == phases.main:
            phases.counts["full_validations"] += 1
            phases.counts["validated_aggregates"] += len(collection._entities)
        with phases.measure("validate"):
            return original_validate(collection, previous)

    def reconcile(changes):
        phases.reconciling = True
        try:
            with phases.measure("reconcile"):
                return prepare(changes)
        finally:
            phases.reconciling = False

    def observe_effective(*args, **kwargs):
        if phases.reconciling:
            phases.counts["reconciled_contexts"] += 1
        return effective(*args, **kwargs)

    stack.enter_context(patch.object(document_payloads, "validate_project", validate))
    stack.enter_context(patch.object(controller.core.entities, "validator", validate))
    stack.enter_context(patch.object(controller.core, "prepare", reconcile))
    stack.enter_context(patch.object(
        controller.cards_service, "effective", observe_effective,
    ))
    partial = getattr(controller.core.entities, "change_validator", None)
    if partial is not None:
        validate_affected = partial._validate_affected
        projection = document_payloads.card_projection
        current_scope = None

        def observe_projection(collection, key):
            if current_scope is not None:
                current_scope.add(key)
            return projection(collection, key)

        def observe_affected(collection, changes, maps):
            nonlocal current_scope
            current_scope = {entry.id for entry in changes.aggregates}
            try:
                with phases.measure("validate"):
                    return validate_affected(collection, changes, maps)
            finally:
                phases.counts["validated_aggregates"] += len(current_scope)
                current_scope = None

        stack.enter_context(patch.object(partial, "_validate_affected", observe_affected))
        stack.enter_context(patch.object(document_payloads, "card_projection", observe_projection))
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
    def count_decodes(name, counter, phase=None):
        original = getattr(SQLiteProjectStore, name)

        def counted(*args, **kwargs):
            phases.counts[counter] += 1
            if phase is None:
                return original(*args, **kwargs)
            with phases.measure(phase):
                return original(*args, **kwargs)

        stack.enter_context(patch.object(SQLiteProjectStore, name, staticmethod(counted)))

    read = (
        "_decode_snapshot" if hasattr(SQLiteProjectStore, "_decode_snapshot") else "_read_snapshot"
    )
    count_decodes(read, "decoded_snapshots", "read_snapshot")
    count_decodes("_load_modules", "decoded_module_batches", "decode_modules")
    connect = sqlite3.connect

    class TimedCursor(sqlite3.Cursor):
        def execute(self, *args, **kwargs):
            with phases.measure("sqlite"):
                result = super().execute(*args, **kwargs)
            if get_ident() != phases.main and self.rowcount > 0:
                phases.counts["changed_sql_rows"] += self.rowcount
            return result

        def executemany(self, *args, **kwargs):
            with phases.measure("sqlite"):
                result = super().executemany(*args, **kwargs)
            if get_ident() != phases.main and self.rowcount > 0:
                phases.counts["changed_sql_rows"] += self.rowcount
            return result

        fetchone = phases.wrap("sqlite", sqlite3.Cursor.fetchone)
        fetchall = phases.wrap("sqlite", sqlite3.Cursor.fetchall)
        __next__ = phases.wrap("sqlite", sqlite3.Cursor.__next__)

    class TimedConnection(sqlite3.Connection):
        __exit__ = phases.wrap("sqlite", sqlite3.Connection.__exit__)
        commit = phases.wrap("sqlite", sqlite3.Connection.commit)

        def execute(self, *args, **kwargs):
            return self.cursor(TimedCursor).execute(*args, **kwargs)

        def executemany(self, *args, **kwargs):
            return self.cursor(TimedCursor).executemany(*args, **kwargs)

    def timed_connect(*args, **kwargs):
        with phases.measure("sqlite"):
            return connect(*args, **kwargs, factory=TimedConnection)

    stack.enter_context(patch.object(sqlite3, "connect", timed_connect))

    def persist(snapshot, *base):
        with phases.measure("write"):
            project.store.save(snapshot, *base)
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
    assert phases.calls["gui", "read_snapshot"] == 0
    started = perf_counter()
    entries = catalogue.entries(())
    listing = (perf_counter() - started) * 1000
    assert all(entry["status"] == "pending" for entry in entries)
    listing_reads = phases.calls["gui", "read_snapshot"]
    # As in ProjectController, use the snapshot obtained inside the writer lease.
    phases.calls.clear()
    selected = entries[0]
    candidate = Path(selected["path"])
    started = perf_counter()
    opened, verified = SQLiteProjectStore.open_with_snapshot(
        candidate, expected=selected["metadata"],
    )
    open_ms = (perf_counter() - started) * 1000
    with closing(opened):
        assert verified.snapshot.revision >= 1
    assert phases.calls["gui", "read_snapshot"] == 1
    return {"three_world_listing_ms": round(listing, 3), "one_world_open_ms": round(open_ms, 3),
            "second_load_ms": 0, "catalogue_full_reads": listing_reads,
            "selected_world_full_reads": 1}


def statistics(records, statistic):
    return {
        name: {
            key: round(statistic([sample.get(key, 0) for sample in samples]), 4)
            for key in sorted(set().union(*(sample.keys() for sample in samples)))
        }
        for name, samples in records.items()
    }


def p95(values):
    return sorted(values)[ceil(0.95 * len(values)) - 1]


def measure_series(app, controller, project, phases, snapshot, document, series_size, acks):
    refs = [
        ActorRef(card.id, actor.id) for card in snapshot.cards for actor in card.actors
    ]
    tokens = document.tokens
    results = {}
    for name in ("actor_hp", "token_move"):
        app.processEvents()
        records = []
        initial_revision = project.saver.revision
        for i in range(series_size):
            phases.reset()
            with phases.measure("edit"):
                if name == "actor_hp":
                    controller.cards_service.update_actor(
                        refs[i % len(refs)], {"hp_current": 10 + (i // len(refs)) % 2},
                    )
                else:
                    controller.maps_service.move_token(
                        document.id, tokens[i % len(tokens)].id, 100 + (i // len(tokens)) % 2, 300,
                    )
            records.append(phases.readings())
        assert project.saver.revision == initial_revision + series_size
        phases.reset()
        prior_io = io_written()
        started = perf_counter()
        assert project.saver.save(), project.saver.last_error
        results[name] = phases.readings() | {
            "samples": records,
            "save_wall_ms": round((perf_counter() - started) * 1000, 4),
            "write_bytes": io_written() - prior_io,
            "worker_to_ack_ms": round(acks.pop(), 4),
        }
    return results


def benchmark(profile, sample_count, root, *, series_size=40, full_validation=False):
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
        if full_validation:
            controller.core.entities.change_validator.full_validation = True
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
        npc_card = snapshot.cards[4]
        structural_actor = None

        def edit_structure(step):
            nonlocal structural_actor
            with controller.core.transaction():
                if step:
                    controller.actions.delete_actor(structural_actor, confirmed=True)
                    controller.actions.update_entity(snapshot.cards[-1].id, parent_id=None)
                else:
                    controller.actions.update_entity(snapshot.cards[-1].id, parent_id=card.id)
                    placement = controller.actions.place_card(document.id, npc_card.id, 80, 95)
                    structural_actor = ActorRef(npc_card.id, placement.actor_id)

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
            "structure": edit_structure,
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
                    phases.reset()
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
            series = measure_series(
                app, controller, project, phases, snapshot, document, series_size, acks,
            )
            catalogue_data = catalogue_reads(root, catalogue, project.store, phases)
        series_samples = {name: data["samples"] for name, data in series.items()}
        return {
            "platform": platform.platform(), "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version, "qt_platform": app.platformName(),
            "profile": dict(zip(
                ("actors", "items", "maps", "tokens", "rows_per_actor"), profile, strict=True,
            )),
            "samples_after_warmup": sample_count,
            "series_size": series_size,
            "db_bytes": project.store.path.stat().st_size,
            "empty_memory_mib": empty_memory, "loaded_memory_mib": loaded_memory,
            "final_memory_mib": memory(),
            "median": statistics(records, median),
            "p95": statistics(records, p95),
            "series_median": statistics(series_samples, median),
            "series_p95": statistics(series_samples, p95),
            "series": series,
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
    parser.add_argument("--series", type=int, default=40)
    parser.add_argument("--full-validation", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="lodandsy-audit-benchmark-") as temporary:
        result = benchmark(
            PROFILES[options.profile], options.samples, Path(temporary), series_size=options.series,
            full_validation=options.full_validation,
        )
    options.report.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
