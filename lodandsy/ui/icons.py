from functools import lru_cache

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from lodandsy.ui.theme import COLORS, ICON_SIZE, ICON_STROKE, TOOL_SIZE

PATHS = {
    "ruler": '<path d="m2 11 9-9 3 3-9 9zM5 8l2 2M8 5l2 2"/>',
    "vertices": '<path d="m2 13 5-10 7 8z"/><rect x="1" y="12" width="2" height="2"/>'
    '<rect x="6" y="2" width="2" height="2"/><rect x="13" y="10" width="2" height="2"/>',
    "brush": '<path d="m7 9 6-7 2 2-7 6M7 9c-3-2-5 1-5 5 4 0 7-2 5-5z"/>',
    "eraser": '<path d="m2 9 7-7 5 5-7 7H5zM6 5l5 5M7 14h8"/>',
    "fog_polygon": '<path d="m2 5 6-3 6 5-3 7H4zM2 5l9 9"/>',
    "fog_select": '<path d="M5 2H2v3M11 2h3v3M2 11v3h3M14 11v3h-3M6 6l6 3-3 1-1 3z"/>',
    "shape_circle": '<circle cx="8" cy="8" r="6"/>',
    "shape_triangle": '<path d="m8 2 6 12H2z"/>',
    "shape_rectangle": '<rect x="2" y="4" width="12" height="8"/>',
    "shape_quadrilateral": '<path d="m3 2 11 3-2 9-10-2z"/>',
    "shape_cone": '<path d="m2 8 12-6v12z"/>',
    "shape_polygon": '<path d="m2 7 4-5 8 4-3 8-6-2z"/>',
    "portal": '<circle cx="8" cy="8" r="6"/><path d="M5 11l6-6M6 5h5v5"/>',
    "vector": '<path d="m2 13 4-10 8 8z"/><circle cx="2" cy="13" r="1"/>'
    '<circle cx="6" cy="3" r="1"/><circle cx="14" cy="11" r="1"/>',
    "race": '<circle cx="8" cy="4" r="3"/><path d="M2 15v-2a6 6 0 0 1 12 0v2"/>',
    "class": '<path d="m3 1 10 10-2 2L1 3zM9 13l4-4M11 15l4-4"/>',
    "subclass": '<path d="m8 1 2 4 5 1-3 4 1 5-5-2-5 2 1-5-3-4 5-1z"/>',
    "level": '<path d="M2 14h4v-4h4V6h4V2"/>',
    "fog": '<path d="M2 6a3 3 0 0 1 5-3 4 4 0 0 1 7 3M1 9h14M3 12h10M5 15h6"/>',
    "monitor": '<rect x="1" y="2" width="14" height="10" rx="1"/><path d="M8 12v3M4 15h8"/>',
    "settings": '<circle cx="8" cy="8" r="3"/>'
    '<path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l2 2M11 11l2 2M3 13l2-2M11 5l2-2"/>',
    "undo": '<path d="M5 4 2 7l3 3M2 7h7a4 4 0 0 1 0 8"/>',
    "redo": '<path d="m11 4 3 3-3 3M14 7H7a4 4 0 0 0 0 8"/>',
    "crop": '<path d="M4 1v11h11M1 4h11v11M13 1 1 13"/>',
    "cursor": '<path d="m3 2 10 6-5 1-2 5z"/>',
    "hand": '<path d="M4 8V4m3 4V2m3 6V3m3 7V5M4 7 2 6v5l4 4h5l3-5"/>',
    "d4": '<path d="M8 1 15 14H1zM8 1v9l7 4M8 10l-7 4"/>',
    "d6": '<rect x="2" y="2" width="12" height="12" rx="1"/>'
    '<path d="M5 5h.01M11 5h.01M5 8h.01M11 8h.01M5 11h.01M11 11h.01"/>',
    "d8": '<path d="m8 1 7 7-7 7-7-7zM1 8h14M8 1l3 7-3 7-3-7z"/>',
    "d10": '<path d="m8 1 7 5-2 7-5 2-5-2-2-7zM8 1 3 13l5-4 5 4L8 1M8 9v6"/>',
    "d12": '<path d="m8 1 6 4v6l-6 4-6-4V5zM5 5h6l2 5-5 3-5-3zM8 1v4M2 5l3 0M14 5h-3"/>',
    "d20": '<path d="m8 1 6 4v6l-6 4-6-4V5zM8 1l4 10H4zM2 5l6 3 6-3M4 11l4 4 4-4"/>',
    "d100": '<path d="m8 1 7 5-2 7-5 2-5-2-2-7zM8 1v14M2 6h12M3 13l5-7 5 7"/>',
    "card": '<path d="M4 2h6l3 3v9H4zM10 2v4h3M6 8h5M6 11h4"/>',
    "card_note": '<path d="M9 2.5H4.5a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h6V11'
    'M2.2 5h2.6M2.2 8h2.6M2.2 11h2.6m3.1-1 1-2.7 4.1-4.1 1.8 1.8-4.1 4.1z"/>',
    "card_article": '<path d="M3.5 2h5.8l3.2 3.2V14h-9zM9.3 2v3.6h3.2'
    'M5.7 7.8h4.6M5.7 10h4.6M5.7 12.2h3"/>',
    "card_character": '<circle cx="8" cy="4.6" r="2.65"/>'
    '<path d="M2.6 13.6v-1a5.4 4 0 0 1 10.8 0v1z"/>',
    "card_item": '<path d="m4.8 9.4 6-6.4 3.3-1.1-1.1 3.3-6.4 6'
    'M3.6 8.4l4 4m-2-2-3.5 3.5"/>',
    "card_location": '<path d="M12.5 6.3c0 3.1-4.5 7.7-4.5 7.7S3.5 9.4 3.5 6.3'
    'a4.5 4.5 0 1 1 9 0z"/>'
    '<circle cx="8" cy="6.3" r="1.5"/>',
    "card_folder": '<path d="M2 4a1 1 0 0 1 1-1h3l1.6 1.7H13a1 1 0 0 1 1 1v6.4a1 1 0 0 1-1 1H3'
    'a1 1 0 0 1-1-1z"/>',
    "card_creature": '<path d="M4 11.8c0-1.3 2.6-4 4-4s4 2.7 4 4c0 1.5-1.6 1.8-2.7 1.2'
    'a2.8 2.8 0 0 0-2.6 0c-1.1.6-2.7.3-2.7-1.2z"/>'
    '<ellipse cx="3" cy="7.1" rx="1.1" ry="1.4" transform="rotate(-25 3 7.1)"/>'
    '<ellipse cx="6.1" cy="4.5" rx="1" ry="1.5"/><ellipse cx="9.9" cy="4.5" rx="1" ry="1.5"/>'
    '<ellipse cx="13" cy="7.1" rx="1.1" ry="1.4" transform="rotate(25 13 7.1)"/>',
    "card_region": '<path d="M1.5 12.75 6.7 3.2l3.2 5.9 1.2-2.1 3.4 5.75z'
    'M4.8 6.7l1.9 1.4 1.9-1.4"/>',
    "card_object": '<path d="M8 2l5.5 3.2v5.6L8 14l-5.5-3.2V5.2zM2.5 5.2 8 8.3l5.5-3.1M8 8.3V14"/>',
    "card_magic": '<path d="M6.2 2.9 7.4 6.4l3.5 1.2-3.5 1.2-1.2 3.5-1.2-3.5-3.5-1.2L5 6.4z'
    'M12.4 2.2v3.4m-1.7-1.7h3.4M12 10.5v3.3m-1.65-1.65h3.3"/>',
    "card_skill": '<circle cx="8" cy="8" r="5.8"/><circle cx="8" cy="8" r="3.15"/>'
    '<path d="M8 8h.01"/>',
    "card_lore": '<path d="M8 4.2C6.1 3 4 2.8 1.8 3.3v9.1c2.2-.5 4.3-.3 6.2.9'
    ' 1.9-1.2 4-1.4 6.2-.9V3.3c-2.2-.5-4.3-.3-6.2.9v9.1M4 6.4l1.8.25M10.2 6.65 12 6.4"/>',
    "map": '<path d="m2 4 4-2 4 2 4-2v10l-4 2-4-2-4 2zM6 2v10M10 4v10"/>',
    "table": '<rect x="2" y="3" width="12" height="10"/><path d="M2 7h12M6 3v10M10 7v6"/>',
    "inventory": '<rect x="3" y="4" width="10" height="10" rx="2"/>'
    '<path d="M6 4V2h4v2M3 8h10M6 11h4"/>',
    "dice": '<rect x="3" y="3" width="10" height="10" rx="2"/>'
    '<path d="M6 6h.01M10 6h.01M8 8h.01M6 10h.01M10 10h.01"/>',
    "loot": '<path d="M6 5 4 2h8l-2 3m-4 0h4l3 4v3a2 2 0 0 1-2 2H5'
    'a2 2 0 0 1-2-2V9zM6 9h4M8 7v4"/>',
    "shop": '<path d="M2 6 4 2h8l2 4v2h-2l-1-1-1 1H6L5 7 4 8H2z'
    'M3 8v6h10V8M6 14v-4h4v4"/>',
    "coins": '<ellipse cx="7" cy="4" rx="5" ry="2"/><path d="M2 4v6c0 1 2 2 5 2'
    'm-5-5c0 1 2 2 5 2m5-5v3"/><circle cx="11" cy="11" r="3"/>',
    "open": '<path d="M3 8h10M9 4l4 4-4 4"/>',
    "search": '<circle cx="7" cy="7" r="4"/><path d="m10 10 4 4"/>',
    "more": '<circle cx="3" cy="8" r=".8"/><circle cx="8" cy="8" r=".8"/>'
    '<circle cx="13" cy="8" r=".8"/>',
    "more_vertical": '<circle cx="8" cy="4" r=".55"/><circle cx="8" cy="8" r=".55"/>'
    '<circle cx="8" cy="12" r=".55"/>',
    "tree": '<path d="M4 3v12h4M4 8h4M8 3h5v4H8zM8 11h5v4H8z"/>',
    "inspector": '<rect x="3" y="2" width="10" height="12" rx="1"/><path d="M6 5h4M6 8h4M6 11h2"/>',
    "plus": '<path d="M8 3v10M3 8h10"/>',
    "minus": '<path d="M3 8h10"/>',
    "copy": '<rect x="5" y="5" width="8" height="9" rx="1"/><path d="M3 10V3h7"/>',
    "repeat": '<path d="M12 5a5 5 0 1 0 1 5M12 2v4H8"/>',
    "clear": '<path d="M3 4h10M6 4V2h4v2M5 7l1 7h4l1-7"/>',
    "backup": '<path d="M2 7h12v7H2zM2 7l2-4h8l2 4M6 10h4"/>',
    "delete": '<path d="M3 4h10M6 4V2h4v2M5 6v7h6V6M7 7v4M9 7v4"/>',
    "rename": '<path d="m3 10 7-7 3 3-7 7H3zM9 4l3 3"/>',
    "fit": '<path d="M6 3H3v3M10 3h3v3M3 10v3h3M13 10v3h-3"/>',
    "link": '<path d="m6 5 2-2a3 3 0 0 1 4 4l-2 2M10 11l-2 2a3 3 0 0 1-4-4l2-2M5 11l6-6"/>',
    "bullet_list": '<path d="M6 4h8M6 8h8M6 12h8M2.5 4h.01M2.5 8h.01M2.5 12h.01"/>',
    "numbered_list": '<path d="M7 4h7M7 8h7M7 12h7M2.5 3l1-1v3M2 8a1 1 0 0 1 2 0'
    'c0 1-2 1.5-2 2.5h2M2 13h2"/>',
    "up": '<path d="m3 10 5-5 5 5"/>',
    "down": '<path d="m3 6 5 5 5-5"/>',
}

TREE_CARD_ICONS = {
    "note": ("card_note", "#A8ADB6"),
    "article": ("card_article", "#A4B7C8"),
    "character": ("card_character", "#83A8C9"),
    "item": ("card_item", "#C4AE7C"),
    "location": ("card_location", "#85B19B"),
    "folder": ("card_folder", "#B4A17D"),
    "creature": ("card_creature", "#BF9290"),
    "region": ("card_region", "#9CAE80"),
    "object": ("card_object", "#A5A4B4"),
    "magic": ("card_magic", "#B29ACB"),
    "skill": ("card_skill", "#83B4B1"),
    "lore": ("card_lore", "#BD9E87"),
}


@lru_cache(maxsize=128)
def icon(name, size=ICON_SIZE, *, stroke_width=ICON_STROKE, tint=None):
    result = QIcon()
    if tint is None:
        colors = (
            (COLORS["text"], (QIcon.Mode.Normal,)),
            (COLORS["focus"], (QIcon.Mode.Active,)),
        )
    else:
        colors = ((tint, (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected)),)
    for color, modes in (*colors, (COLORS["disabled"], (QIcon.Mode.Disabled,))):
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" '
            f'fill="none" stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" '
            f'stroke-linejoin="round">{PATHS[name]}</svg>'
        )
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        for ratio in [1, 2, 3]:
            pixmap = QPixmap(size * ratio, size * ratio)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            pixmap.setDevicePixelRatio(ratio)
            for mode in modes:
                result.addPixmap(pixmap, mode)
    return result


def tree_card_icon(card_type):
    appearance = TREE_CARD_ICONS.get(card_type)
    if appearance is None:
        return icon("card")
    name, tint = appearance
    return icon(name, tint=tint)


def configure_tool_button(button, name, label):
    button.setProperty("uiRole", "tool")
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    button.setIcon(icon(name))
    button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
    button.setFixedSize(TOOL_SIZE, TOOL_SIZE)
    button.setAccessibleName(label)
    button.setToolTip(label)
    button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return button
