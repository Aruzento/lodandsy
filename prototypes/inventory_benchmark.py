"""10k public catalog/model-view picker and addressed inventory updates, without other features."""

import argparse
import json
import platform
import time
from pathlib import Path

from PySide6 import __version__ as qt_version
from PySide6.QtWidgets import QApplication, QWidget

from lodandsy.application.cards_service import CardsService
from lodandsy.application.entity_queries import EntityQueries
from lodandsy.application.entity_session import EntitySession
from lodandsy.application.tables_controller import TablesController
from lodandsy.application.tables_service import TablesService
from lodandsy.domain.card import Card
from lodandsy.domain.card_collection import CardCollection
from lodandsy.domain.currency import CoinAmount
from lodandsy.domain.table_document import RowRecord, inventory_columns
from lodandsy.ui.entity_picker import EntityPicker


def milliseconds(start):
    return (time.perf_counter() - start) * 1000


def stats(values):
    return dict(
        p50_ms=sorted(values)[len(values) // 2],
        p95_ms=sorted(values)[int(len(values) * 0.95)],
        max_ms=max(values),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    app = QApplication([])
    start = time.perf_counter()
    collection = CardCollection(
        tuple(
            Card(f"Предмет {i:05}", card_type="item", values=(("aliases", (f"Alias {i:05}",)),))
            for i in range(10_000)
        )
    )
    core = EntitySession(collection.entities)
    cards = CardsService(collection, core=core)
    queries = EntityQueries(core, cards.reference_info)
    cards.card_changed.connect(queries.refresh)
    setup_ms = milliseconds(start)
    start = time.perf_counter()
    picker = EntityPicker(queries, inventory_columns()[0])
    picker_ms = milliseconds(start)
    samples = []
    for i in range(60):
        start = time.perf_counter()
        picker.model.filter(("предмет 00", "alias 00042", "missing")[i % 3])
        samples.append(milliseconds(start))
    assert len(picker.findChildren(QWidget)) < 30
    service = TablesService(core, references=queries)
    table = service.create_table("Inventory", columns=inventory_columns())
    target, other = collection.all()[:2]
    table = service.edit_table(
        table.id,
        rows=tuple(
            RowRecord(
                i,
                (
                    (table.columns[0].id, target.id if i % 2 == 0 else other.id),
                    (table.columns[1].id, 1),
                ),
            )
            for i in range(1000)
        ),
    )
    # No AppShell, Card Editor, Map, Dice or window manager are required by this owner.
    views = TablesController(QWidget(), None, service)
    first, second = views.table_view(table.id), views.table_view(table.id)
    addressed, resets = [], []
    first.model.dataChanged.connect(lambda a, b, *roles: addressed.append((a.row(), a.column())))
    first.model.modelReset.connect(lambda: resets.append(1))
    update_samples = []
    for i in range(30):
        addressed.clear()
        start = time.perf_counter()
        cards.update_card_fields(
            target.id,
            {"cost": CoinAmount(service.currency.base_id, i), "summary": f"Description {i}"},
        )
        update_samples.append(milliseconds(start))
        assert len(addressed) == 1500 and all(row % 2 == 0 for row, col in addressed)
        assert second.model.data(second.model.index(0, 3)) == f"{i} зм"
    assert not resets and len(service.get_table(table.id).rows[0].cells) == 2
    result = dict(
        platform=platform.platform(),
        python=platform.python_version(),
        qt=qt_version,
        catalog_entities=10000,
        inventory_rows=1000,
        views=2,
        catalog_setup_ms=setup_ms,
        picker_create_ms=picker_ms,
        picker_widgets=len(picker.findChildren(QWidget)),
        filter=stats(samples),
        item_update_500_rows=stats(update_samples),
        update_signals_per_view=1500,
        model_resets=len(resets),
        unrelated_rows_updated=0,
        note="Synthetic fixed workload, offscreen; excludes physical input latency.",
    )
    args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    picker.deleteLater()
    first.deleteLater()
    second.deleteLater()
    app.processEvents()


if __name__ == "__main__":
    main()
