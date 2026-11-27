"""Qt geometry adapter; returns immutable numeric domain geometry only."""

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QPolygonF

from lodandsy.domain.map_fog import MAX_GESTURE_POINTS, FogRegion, FogState

MAX_BRUSH_POINTS = 4096


def region_path(region):
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    for ring in region.rings:
        path.addPolygon(QPolygonF([QPointF(*p) for p in ring]))
        path.closeSubpath()
    return path


def state_path(state):
    result = QPainterPath()
    result.setFillRule(Qt.FillRule.WindingFill)
    for region in state.regions:
        # Normalize each odd-even region first, including loaded intersecting rings.
        # This keeps all region contributions nonnegative and prevents winding cancellation.
        polygons = region_path(region).simplified().toSubpathPolygons()
        rings = [tuple((p.x(), p.y()) for p in polygon) for polygon in polygons]
        paths = []
        for polygon in polygons:
            path = QPainterPath()
            path.addPolygon(polygon)
            path.closeSubpath()
            paths.append(path)
        for i, ring in enumerate(rings):
            depth = sum(path.contains(paths[i]) for j, path in enumerate(paths) if j != i)
            area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, (*ring[1:], ring[0])))
            points = ring if (area > 0) == (depth % 2 == 0) else tuple(reversed(ring))
            result.addPolygon(QPolygonF([QPointF(*point) for point in points]))
            result.closeSubpath()
    return result


def path_region(path, key=None):
    rings = []
    for polygon in path.toSubpathPolygons():
        points = tuple((p.x(), p.y()) for p in polygon)
        if points and points[0] == points[-1]:
            points = points[:-1]
        if len(points) >= 3:
            rings.append(points)
    if not rings:
        return None
    return FogRegion(tuple(rings), **({"id": key} if key else {}))


def brush_stamp(center, diameter):
    path = QPainterPath()
    path.addEllipse(center, diameter / 2, diameter / 2)
    return path


def stroke_path(points, diameter):
    _validate_points(points)
    return brush_stroke_path(points, diameter)


def brush_stroke_path(points, diameter):
    _validate_points(points, MAX_BRUSH_POINTS)
    if not points or not math.isfinite(diameter) or not 1 <= diameter <= 100000:
        raise ValueError("Слишком длинный жест или некорректный размер кисти")
    if len(points) == 1:
        return brush_stamp(QPointF(*points[0]), diameter)
    path = QPainterPath(QPointF(*points[0]))
    for p in points[1:]:
        path.lineTo(QPointF(*p))
    stroker = QPainterPathStroker()
    stroker.setWidth(diameter)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    result = stroker.createStroke(path)
    for p in (points[0], points[-1]):
        result = result.united(brush_stamp(QPointF(*p), diameter))
    return result


def polygon_path(points):
    _validate_points(points)
    if not 3 <= len(points) <= MAX_GESTURE_POINTS or len(set(points)) != len(points):
        raise ValueError("Нужен простой многоугольник с3–512 различными вершинами")

    # Reject crossings, non-adjacent touches and collinear overlaps before Qt normalization.
    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    edges = list(zip(points, (*points[1:], points[0])))
    for i, (a, b) in enumerate(edges):
        for j, (c, d) in enumerate(edges[i + 1 :], i + 1):
            if j == i + 1 or i == 0 and j == len(edges) - 1:
                continue
            if (
                max(min(a[0], b[0]), min(c[0], d[0])) <= min(max(a[0], b[0]), max(c[0], d[0]))
                and max(min(a[1], b[1]), min(c[1], d[1])) <= min(max(a[1], b[1]), max(c[1], d[1]))
                and cross(a, b, c) * cross(a, b, d) <= 0
                and cross(c, d, a) * cross(c, d, b) <= 0
            ):
                raise ValueError("Многоугольник пересекает сам себя")
    region = FogRegion((tuple(points),))
    return region_path(region)


def _validate_points(points, limit=MAX_GESTURE_POINTS):
    if len(points) > limit or any(
        not isinstance(p, (tuple, list))
        or len(p) != 2
        or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e9 for v in p)
        for p in points
    ):
        raise ValueError("Некорректные точки жеста")


def decode_fog(source):
    import json

    if not isinstance(source, str) or len(source.encode("utf-8")) > 8 * 2**20:
        raise ValueError("Fog payload exceeds8MiB")
    rows = json.loads(source)
    if not isinstance(rows, list) or len(rows) > 256:
        raise ValueError("Invalid fog payload")
    regions = []
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.keys() != {"id", "rings"}
            or not isinstance(row["rings"], list)
        ):
            raise ValueError("Unsupported fog region structure")
        if any(
            not isinstance(r, list) or any(not isinstance(p, list) for p in r) for r in row["rings"]
        ):
            raise ValueError("Invalid fog ring structure")
        regions.append(
            FogRegion(tuple(tuple(tuple(p) for p in ring) for ring in row["rings"]), row["id"])
        )
    return FogState(tuple(regions))


def apply_fog(state, path, *, erase=False):
    if erase:
        regions = []
        bounds = path.boundingRect()
        for region in state.regions:
            previous = region_path(region)
            result = (
                path_region(previous.subtracted(path), region.id)
                if bounds.intersects(previous.boundingRect())
                else region
            )
            if result:
                regions.append(result)
        regions = tuple(regions)
    else:
        region = path_region(path)
        regions = (*state.regions, region) if region else state.regions
    return FogState(regions)
