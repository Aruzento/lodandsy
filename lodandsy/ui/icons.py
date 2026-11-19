from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    "d4": '<path d="M8 1 15 14H1zM8 1v9l7 4M8 10l-7 4"/>',
    "d6": '<rect x="2" y="2" width="12" height="12" rx="1"/>'
          '<path d="M5 5h.01M11 5h.01M5 8h.01M11 8h.01M5 11h.01M11 11h.01"/>',
    "d8": '<path d="m8 1 7 7-7 7-7-7zM1 8h14M8 1l3 7-3 7-3-7z"/>',
    "d10": '<path d="m8 1 7 5-2 7-5 2-5-2-2-7zM8 1 3 13l5-4 5 4L8 1M8 9v6"/>',
    "d12": '<path d="m8 1 6 4v6l-6 4-6-4V5zM5 5h6l2 5-5 3-5-3zM8 1v4M2 5l3 0M14 5h-3"/>',
    "d20": '<path d="m8 1 6 4v6l-6 4-6-4V5zM8 1l4 10H4zM2 5l6 3 6-3M4 11l4 4 4-4"/>',
    "d100": '<path d="m8 1 7 5-2 7-5 2-5-2-2-7zM8 1v14M2 6h12M3 13l5-7 5 7"/>',
    "card": '<path d="M4 2h6l3 3v9H4zM10 2v4h3M6 8h5M6 11h4"/>',
    "map": '<path d="m2 4 4-2 4 2 4-2v10l-4 2-4-2-4 2zM6 2v10M10 4v10"/>',
    "table": '<rect x="2" y="3" width="12" height="10"/><path d="M2 7h12M6 3v10M10 7v6"/>',
    "dice": '<rect x="3" y="3" width="10" height="10" rx="2"/>'
            '<path d="M6 6h.01M10 6h.01M8 8h.01M6 10h.01M10 10h.01"/>',
    "open": '<path d="M3 8h10M9 4l4 4-4 4"/>',
    "search": '<circle cx="7" cy="7" r="4"/><path d="m10 10 4 4"/>',
    "more": '<circle cx="3" cy="8" r=".8"/><circle cx="8" cy="8" r=".8"/>'
            '<circle cx="13" cy="8" r=".8"/>',
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


def icon(name, size=16):
    result = QIcon()
    for mode, color in [(QIcon.Mode.Normal, "#e8edf4"), (QIcon.Mode.Active, "#ceb075"),
                        (QIcon.Mode.Disabled, "#7e8ca2")]:
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" '
               f'fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" '
               f'stroke-linejoin="round">{PATHS[name]}</svg>')
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        for ratio in [1, 2, 3]:
            pixmap = QPixmap(size * ratio, size * ratio)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            pixmap.setDevicePixelRatio(ratio)
            result.addPixmap(pixmap, mode)
    return result
