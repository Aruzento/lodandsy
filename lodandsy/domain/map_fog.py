"""Canonical bounded numeric geometry. No Qt types or raster masks."""

import math
from dataclasses import dataclass, field
from uuid import uuid4

from lodandsy.domain.module_values import validate_id

MAX_REGIONS = 256
MAX_REGION_POINTS = 8192
MAX_TOTAL_POINTS = 65536
MAX_GESTURE_POINTS = 512


@dataclass(frozen=True, slots=True)
class FogRegion:
    rings: tuple
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self):
        validate_id(self.id)
        if not isinstance(self.rings, tuple) or not self.rings:
            raise ValueError("Область тумана пуста")
        if sum(len(ring) for ring in self.rings) > MAX_REGION_POINTS:
            raise ValueError("Слишком сложная область тумана (8192 вершины)")
        for ring in self.rings:
            if not isinstance(ring, tuple) or len(ring) < 3:
                raise ValueError("Контур должен содержать три вершины")
            for point in ring:
                if (
                    not isinstance(point, tuple)
                    or len(point) != 2
                    or any(
                        type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e9
                        for v in point
                    )
                ):
                    raise ValueError("Некорректная координата тумана")
            if (
                abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, (*ring[1:], ring[0]))))
                < 1e-6
            ):
                raise ValueError("Вырожденный контур тумана")


@dataclass(frozen=True, slots=True)
class FogState:
    regions: tuple[FogRegion, ...] = ()

    def __post_init__(self):
        if not isinstance(self.regions, tuple) or not all(
            isinstance(r, FogRegion) for r in self.regions
        ):
            raise ValueError("Некорректный туман карты")
        if len(self.regions) > MAX_REGIONS or len({r.id for r in self.regions}) != len(
            self.regions
        ):
            raise ValueError("Слишком много областей тумана или повторный ID")
        if sum(len(p) for r in self.regions for p in r.rings) > MAX_TOTAL_POINTS:
            raise ValueError("Туман превышает бюджет65536 вершин")
