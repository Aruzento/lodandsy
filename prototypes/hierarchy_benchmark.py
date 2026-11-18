"""Repeatable in-memory hierarchy measurements; not a GUI benchmark or SLA."""

import json
import sys
import tracemalloc
from time import perf_counter
from uuid import UUID

from lodandsy.domain.card import Card
from lodandsy.domain.card_collection import CardCollection


def main():
    results = []
    for count in [10_000, 50_000]:
        for profile in ["wide", "deep"]:
            tracemalloc.start()
            started = perf_counter()
            ids = [str(UUID(int=i + 1)) for i in range(count)]
            cards = CardCollection(
                Card(str(i), id=card_id,
                     parent_id=(ids[i - 1] if profile == "deep" else ids[0]) if i else None)
                for i, card_id in enumerate(ids)
            )
            loaded = perf_counter()
            descendants = cards.descendant_ids(ids[0])
            traversed = perf_counter()
            deleted = cards.delete(ids[0])
            finished = perf_counter()
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            assert len(descendants) == count - 1 and len(deleted) == count
            results.append({
                "count": count, "profile": profile,
                "load_ms": round((loaded - started) * 1000, 2),
                "walk_ms": round((traversed - loaded) * 1000, 2),
                "delete_ms": round((finished - traversed) * 1000, 2),
                "peak_mib": round(peak / 1024**2, 2),
            })
    print(json.dumps({"python": sys.version, "results": results}, indent=2))


if __name__ == "__main__":
    main()
