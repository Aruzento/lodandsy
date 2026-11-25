"""Pure map calibration; no movement costs or routing."""

import math


def distance(grid, origin, target, mode="grid"):
    if mode not in {"grid", "geometry"}:
        raise ValueError("Unknown measurement mode")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (*origin, *target)):
        raise ValueError("Invalid measurement position")
    if grid.feet_per_cell is None:
        return None
    dx, dy = abs(target[0] - origin[0]), abs(target[1] - origin[1])
    length = max(dx, dy) if mode == "grid" else math.hypot(dx, dy)
    return length * grid.feet_per_cell / grid.cell_size
