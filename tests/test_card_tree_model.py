from uuid import uuid4

from PySide6.QtCore import QModelIndex, QSize, Qt
from PySide6.QtGui import QColor, QIcon

from lodandsy.domain.card import Card
from lodandsy.domain.card_schema import CARD_TYPES
from lodandsy.domain.document_payloads import project_entities
from lodandsy.domain.entity import Entity
from lodandsy.ui.icons import TREE_CARD_ICONS, icon, tree_card_icon
from lodandsy.ui.project_tree_model import ProjectTreeModel
from lodandsy.ui.theme import COLORS, ICON_SIZE


def test_card_tree_icons_cover_canonical_types_and_keep_color_in_selection():
    assert TREE_CARD_ICONS.keys() == CARD_TYPES.keys()
    size = QSize(ICON_SIZE, ICON_SIZE)
    silhouettes = set()

    def luminance(color):
        rgb = (color.redF(), color.greenF(), color.blueF())
        linear = (
            value / 12.92 if value <= 0.04045 else ((value + .055) / 1.055) ** 2.4
            for value in rgb
        )
        return sum(channel * weight for channel, weight in zip(linear, (.2126, .7152, .0722)))

    for card_type, (_, tint) in TREE_CARD_ICONS.items():
        decoration = tree_card_icon(card_type)
        for background in ("input", "hover", "selection"):
            assert (
                (luminance(QColor(tint)) + .05) / (luminance(QColor(COLORS[background])) + .05)
            ) >= 3
        normal = decoration.pixmap(size, 2.0, QIcon.Mode.Normal).toImage()
        assert normal.size() == size * 2
        for mode in (QIcon.Mode.Active, QIcon.Mode.Selected):
            assert normal == decoration.pixmap(size, 2.0, mode).toImage()
        opaque = []
        for y in range(normal.height()):
            for x in range(normal.width()):
                if normal.pixelColor(x, y).alpha() == 255:
                    assert normal.pixelColor(x, y) == QColor(tint)
                    opaque.append((x, y))
        assert opaque
        silhouettes.add(tuple(opaque))
    assert len(silhouettes) == len(CARD_TYPES)


def test_tree_projection_uses_neutral_fallback_and_keeps_map_and_table_icons():
    card = Card("Одинаковое название")
    world = project_entities([card]).summaries()
    map_, table = (
        Entity(str(uuid4()), kind, card.title, position=position)
        for position, kind in enumerate(("map", "table"), start=1)
    )
    model = ProjectTreeModel()
    model.set_entities((*world, map_, table))
    row = model.index_for_node(f"card:{card.id}")
    assert row.data(Qt.ItemDataRole.DecorationRole).cacheKey() == icon("card").cacheKey()
    model.set_entities((*world, map_, table), card_types={card.id: "item"})
    assert row.data(Qt.ItemDataRole.DecorationRole).cacheKey() == tree_card_icon("item").cacheKey()
    assert row.data(Qt.ItemDataRole.ForegroundRole) is None
    assert row.data(Qt.ItemDataRole.BackgroundRole) is None
    model.set_entities((*world, map_, table), card_types={card.id: "unknown"})
    for kind, key in (("card", card.id), ("map", map_.id), ("table", table.id)):
        row = model.index_for_node(f"{kind}:{key}")
        assert row.data(Qt.ItemDataRole.DecorationRole).cacheKey() == icon(kind).cacheKey()


def test_drop_requests_reparent(qtbot) -> None:
    world = Card(title="World")

    kingdom = Card(
        title="Kingdom",
        parent_id=world.id,
    )
    city = Card(
        title="City",
        parent_id=world.id,
    )

    model = ProjectTreeModel()
    model.set_entities(project_entities([world, kingdom, city]).summaries())

    world_index = model.index(0, 0)
    kingdom_index = model.index(
        0,
        0,
        world_index,
    )
    city_index = model.index(
        1,
        0,
        world_index,
    )

    mime_data = model.mimeData([city_index])

    with qtbot.waitSignal(
        model.reparent_requested,
        timeout=1000,
    ) as signal:
        handled = model.dropMimeData(
            mime_data,
            Qt.DropAction.MoveAction,
            -1,
            -1,
            kingdom_index,
        )

    assert handled
    assert signal.args == [
        city.id,
        kingdom.id,
    ]


def test_drop_on_root_requests_root_parent(
    qtbot,
) -> None:
    world = Card(title="World")

    city = Card(
        title="City",
        parent_id=world.id,
    )

    model = ProjectTreeModel()
    model.set_entities(project_entities([world, city]).summaries())

    world_index = model.index(0, 0)
    city_index = model.index(
        0,
        0,
        world_index,
    )

    mime_data = model.mimeData([city_index])

    with qtbot.waitSignal(
        model.reparent_requested,
        timeout=1000,
    ) as signal:
        handled = model.dropMimeData(
            mime_data,
            Qt.DropAction.MoveAction,
            -1,
            -1,
            QModelIndex(),
        )

    assert handled
    assert signal.args == [
        city.id,
        None,
    ]


def test_drop_between_rows_requests_validated_move(qtbot) -> None:
    first = Card(title="First")
    second = Card(title="Second")

    model = ProjectTreeModel()
    model.set_entities(project_entities([first, second]).summaries())

    first_index = model.index(0, 0)
    mime_data = model.mimeData([first_index])

    with qtbot.waitSignal(model.move_requested) as signal:
        assert model.dropMimeData(mime_data, Qt.DropAction.MoveAction, 2, 0, QModelIndex())
    assert signal.args == [first.id, None, 1]
    assert not model.canDropMimeData(
        mime_data, Qt.DropAction.MoveAction, 3, 0, QModelIndex()
    )


def test_drop_into_descendant_is_rejected() -> None:
    world = Card(title="World")

    kingdom = Card(
        title="Kingdom",
        parent_id=world.id,
    )
    city = Card(
        title="City",
        parent_id=kingdom.id,
    )

    model = ProjectTreeModel()
    model.set_entities(project_entities([world, kingdom, city]).summaries())

    world_index = model.index(0, 0)
    kingdom_index = model.index(
        0,
        0,
        world_index,
    )
    city_index = model.index(
        0,
        0,
        kingdom_index,
    )

    mime_data = model.mimeData([world_index])

    assert not model.canDropMimeData(
        mime_data,
        Qt.DropAction.MoveAction,
        -1,
        -1,
        city_index,
    )
