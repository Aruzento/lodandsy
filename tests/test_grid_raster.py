from types import SimpleNamespace

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter

from lodandsy.domain.map_document import MapGrid
from lodandsy.ui.map_annotations import GridLayer
from lodandsy.ui.map_widget import MapView


@pytest.mark.parametrize("zoom", [0.125, 0.73, 1.37, 2])
@pytest.mark.parametrize("dpr", [1, 1.25, 2])
def test_grid_has_one_physical_pixel_and_repeatable_raster(qapp, zoom, dpr):
    view = MapView()
    view.resize(320, 240)
    view.map_width = view.map_height = 10000
    layer = GridLayer(MapGrid(cell_size=64, opacity=1), view)

    def draw():
        canvas = QImage(int(320 * dpr), int(240 * dpr), QImage.Format.Format_RGB32)
        canvas.setDevicePixelRatio(dpr)
        canvas.fill(0xFF101010)
        painter = QPainter(canvas)
        painter.translate(0.31, 0.67)
        painter.scale(zoom, zoom)
        layer.paint(painter, SimpleNamespace(exposedRect=QRectF(0, 0, 10000, 10000)))
        painter.end()
        return canvas

    image = draw()
    assert image == draw()
    # A row away from horizontal lines contains isolated one-pixel vertical lines.
    rows = []
    for y in range(3, min(image.height(), 50)):
        bright = [x for x in range(3, image.width() - 3) if image.pixelColor(x, y).red() > 100]
        if bright and len(bright) < image.width() // 4:
            rows.append(bright)
    assert rows
    assert all(b - a > 1 for a, b in zip(rows[0], rows[0][1:]))
    view.deleteLater()
