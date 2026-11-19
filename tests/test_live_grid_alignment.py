from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PySide6.QtCore import QPoint, QPointF, QRectF
from PySide6.QtGui import QImage, QPainter

from lodandsy.domain.card import Card
from lodandsy.domain.map_document import MapDocument, MapGrid, TokenInstance
from lodandsy.ui.map_widget import MapView


@pytest.mark.parametrize("zoom", [0.73, 1.37, 4.0])
@pytest.mark.parametrize("dpr", [1.0, 1.25, 1.5, 2.0])
def test_actual_viewport_grid_is_clipped_to_background_and_world_coordinates(qtbot, zoom, dpr):
    view = MapView()
    qtbot.addWidget(view)
    view.resize(720, 480)
    view.show()
    tile = QImage(240, 160, QImage.Format.Format_RGB32)
    tile.fill(0xFF104010)

    class Tiles:
        ready = SimpleNamespace(connect=lambda callback: None)

        def get(self, path):
            return tile

    pyramid = SimpleNamespace(
        width=240, height=160, max_level=0, tile_path=lambda *a: Path("unused")
    )
    view.set_pyramid(pyramid, Tiles())
    card = Card("Card")
    token = TokenInstance(card.id, 100, 90)
    document = MapDocument(
        "Map", str(uuid4()), tokens=(token,), grid=MapGrid(cell_size=40, color="#ff0000", opacity=1)
    )
    for step in range(3):
        view.resize(720 - step * 35, 480 + step * 13)
        view.resetTransform()
        view.scale(zoom, zoom)
        view.centerOn(95 + step * 25, 70 + step * 15)
        view.set_annotations(document, lambda key: card, None, {}, lambda *a: None)
        qtbot.wait(5)
        viewport = view.viewport()
        canvas = QImage(
            round((viewport.width() + 50) * dpr),
            round((viewport.height() + 50) * dpr),
            QImage.Format.Format_RGB32,
        )
        canvas.setDevicePixelRatio(dpr)
        canvas.fill(0xFF010101)
        painter = QPainter(canvas)
        viewport.render(painter, QPoint(17, 23))
        painter.end()
        transform = view.viewportTransform()
        expected = (
            transform.mapRect(QRectF(0, 0, 240, 160))
            .intersected(QRectF(viewport.rect()))
            .translated(17, 23)
        )
        red = []
        for y in range(canvas.height()):
            for x in range(canvas.width()):
                color = canvas.pixelColor(x, y)
                if color.red() > 200 and color.green() < 30 and color.blue() < 30:
                    red.append((x, y))
        assert red
        assert all(
            expected.adjusted(-2 / dpr, -2 / dpr, 2 / dpr, 2 / dpr).contains(
                QPointF(x / dpr, y / dpr)
            )
            for x, y in red
        )
        # A known vertical world line must land over its expected map coordinate.
        point = transform.map(QPointF(40, 25))
        if viewport.rect().contains(point.toPoint()):
            x, y = round((point.x() + 17) * dpr), round((point.y() + 23) * dpr)
            assert any(
                canvas.pixelColor(xx, yy).red() > 200 and canvas.pixelColor(xx, yy).green() < 30
                for xx in range(max(0, x - 2), min(canvas.width(), x + 3))
                for yy in range(max(0, y - 2), min(canvas.height(), y + 3))
            )
        document = replace(document, tokens=(replace(token, x=120 + step * 10),))
