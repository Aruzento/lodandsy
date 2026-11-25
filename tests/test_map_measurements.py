import math

import pytest

from lodandsy.domain.map_document import MapGrid
from lodandsy.domain.map_measurements import distance


@pytest.mark.parametrize(
    "target,grid_value,geometry",
    [
        ((192, 192), 15, 15 * math.sqrt(2)),
        ((256, 192), 20, 25),
        ((-192, 0), 15, 15),
        ((0, 0), 0, 0),
    ],
)
def test_measurement_modes(target, grid_value, geometry):
    grid = MapGrid(feet_per_cell=5)
    assert distance(grid, (0, 0), target) == pytest.approx(grid_value)
    assert distance(grid, (0, 0), target, "geometry") == pytest.approx(geometry)
    assert distance(MapGrid(feet_per_cell=10), (0, 0), target) == pytest.approx(grid_value * 2)


def test_missing_scale_and_nonfinite():
    assert distance(MapGrid(), (0, 0), (10, 10)) is None
    with pytest.raises(ValueError):
        distance(MapGrid(), (0, 0), (math.nan, 1))
