from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    "tree": '<path d="M4 3v12h4M4 8h4M8 3h5v4H8zM8 11h5v4H8z"/>',
    "inspector": '<rect x="3" y="2" width="10" height="12" rx="1"/>'
                 '<path d="M6 5h4M6 8h4M6 11h2"/>',
    "plus": '<path d="M8 3v10M3 8h10"/>',
    "delete": '<path d="M3 4h10M6 4V2h4v2M5 6v7h6V6M7 7v4M9 7v4"/>',
    "rename": '<path d="m3 10 7-7 3 3-7 7H3zM9 4l3 3"/>',
    "fit": '<path d="M6 3H3v3M10 3h3v3M3 10v3h3M13 10v3h-3"/>',
    "link": '<path d="m6 5 2-2a3 3 0 0 1 4 4l-2 2M10 11l-2 2a3 3 0 0 1-4-4l2-2M5 11l6-6"/>',
    "up": '<path d="m3 10 5-5 5 5"/>',
    "down": '<path d="m3 6 5 5 5-5"/>',
}


def icon(name):
    result = QIcon()
    for mode, color in [(QIcon.Mode.Normal, "#e8edf4"), (QIcon.Mode.Active, "#ceb075"),
                        (QIcon.Mode.Disabled, "#7e8ca2")]:
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" '
               f'fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" '
               f'stroke-linejoin="round">{PATHS[name]}</svg>')
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        for ratio in [1, 2, 3]:
            pixmap = QPixmap(16 * ratio, 16 * ratio)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            pixmap.setDevicePixelRatio(ratio)
            result.addPixmap(pixmap, mode)
    return result
