import math
from dataclasses import dataclass, field
from uuid import uuid4

from lodandsy.domain.map_fog import FogState
from lodandsy.domain.module_values import validate_id, validate_title


def _number(value, minimum, maximum, label):
    if (
        type(value) not in (int, float)
        or not minimum <= value <= maximum
        or not math.isfinite(value)
    ):
        raise ValueError(f"Некорректное значение: {label}")


@dataclass(frozen=True, slots=True)
class MapGrid:
    enabled: bool = True
    cell_size: float = 64
    offset_x: float = 0
    offset_y: float = 0
    opacity: float = 0.25
    color: str = "#ffffff"
    feet_per_cell: float | None = None

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("Некорректные настройки сетки")
        if (
            not isinstance(self.color, str)
            or len(self.color) != 7
            or self.color[0] != "#"
            or any(c not in "0123456789abcdefABCDEF" for c in self.color[1:])
        ):
            raise ValueError("Некорректный цвет сетки")
        _number(self.cell_size, 1, 1_000_000, "размер клетки")
        _number(self.offset_x, -1e9, 1e9, "смещение X")
        _number(self.offset_y, -1e9, 1e9, "смещение Y")
        _number(self.opacity, 0, 1, "прозрачность")
        if self.feet_per_cell is not None:
            _number(self.feet_per_cell, 0.01, 1e9, "футов на клетку")


@dataclass(frozen=True, slots=True)
class TokenInstance:
    card_id: str
    x: float
    y: float
    id: str = field(default_factory=lambda: str(uuid4()))
    cells_w: int | None = None
    cells_h: int | None = None
    z: int = 0
    label_override: str | None = None
    image_override: str | None = None
    kind_override: str | None = None
    layer_id: str | None = None
    actor_id: str | None = None

    def __post_init__(self):
        for value in (self.id, self.card_id):
            validate_id(value)
        for value in (self.image_override, self.layer_id, self.actor_id):
            if value is not None:
                validate_id(value)
        if self.kind_override not in {None, "character", "item"}:
            raise ValueError("Некорректный вид токена")
        if self.label_override is not None:
            object.__setattr__(self, "label_override", validate_title(self.label_override))
        for value in (self.x, self.y):
            _number(value, 0, 1e9, "координата токена")
        for value in (self.cells_w, self.cells_h):
            if value is not None and (type(value) is not int or not 1 <= value <= 100):
                raise ValueError("Footprint must contain 1..100 cells")
        if type(self.z) is not int or not 0 <= self.z <= 10000:
            raise ValueError("Некорректный порядок токена")


@dataclass(frozen=True, slots=True)
class TokenPresentation:
    label: str
    asset_id: str | None
    kind: str
    cells_w: int
    cells_h: int
    missing: bool = False
    summary: str = ""
    crop: tuple = (0.0, 0.0, 1.0, 1.0)


def resolve_token(token, card):
    from lodandsy.domain.card_schema import CARD_TYPES

    if card is None:
        return TokenPresentation(
            "Разорванная ссылка · " + token.card_id[:8],
            token.image_override,
            token.kind_override or "character",
            token.cells_w or 1,
            token.cells_h or 1,
            True,
        )
    portrait = card.portrait.asset_id if card.portrait else None
    return TokenPresentation(
        token.label_override if token.label_override is not None else card.title,
        token.image_override or card.value("token_image") or portrait,
        token.kind_override or card.value("token_kind") or CARD_TYPES[card.card_type].token_kind,
        token.cells_w or card.value("token_cells_w") or 1,
        token.cells_h or card.value("token_cells_h") or 1,
        False,
        " · ".join(
            filter(
                None,
                [
                    card.value("summary"),
                    *(
                        f"{key.upper()}: {card.value(key)}"
                        for key in ("hp_max", "ac", "speed")
                        if card.value(key) is not None
                    ),
                ],
            )
        ),
        card.portrait.crop
        if card.portrait and not token.image_override and not card.value("token_image")
        else (0.0, 0.0, 1.0, 1.0),
    )


@dataclass(frozen=True, slots=True)
class MapLayer:
    title: str
    id: str = field(default_factory=lambda: str(uuid4()))
    position: int = 0
    visible: bool = True

    def __post_init__(self):
        validate_id(self.id)
        object.__setattr__(self, "title", validate_title(self.title))
        if (
            type(self.position) is not int
            or not 0 <= self.position < 1000
            or type(self.visible) is not bool
        ):
            raise ValueError("Некорректный слой карты")


@dataclass(frozen=True, slots=True)
class PlacedAssetObject:
    layer_id: str
    asset_id: str
    x: float
    y: float
    width: float
    height: float
    id: str = field(default_factory=lambda: str(uuid4()))
    rotation: float = 0
    z: int = 0
    kind: str = "raster"

    def __post_init__(self):
        for key in (self.id, self.layer_id, self.asset_id):
            validate_id(key)
        for value in (self.x, self.y):
            _number(value, 0, 1e9, "координата объекта")
        for value in (self.width, self.height):
            _number(value, 0.01, 1e7, "размер объекта")
        _number(self.rotation, -360, 360, "поворот")
        if self.kind != "raster" or type(self.z) is not int or not 0 <= self.z < 10000:
            raise ValueError("Неподдерживаемый объект карты")


def validate_map_contents(tokens, grid, layers, objects):
    if (
        not isinstance(tokens, tuple)
        or not all(isinstance(t, TokenInstance) for t in tokens)
        or not isinstance(grid, MapGrid)
        or not isinstance(layers, tuple)
        or not all(isinstance(layer, MapLayer) for layer in layers)
        or not isinstance(objects, tuple)
        or not all(isinstance(o, PlacedAssetObject) for o in objects)
    ):
        raise ValueError("Invalid map content")
    ids = [t.id for t in (*tokens, *layers, *objects)]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate map object ID")
    if len(layers) > 1000 or len(objects) > 10000 or len(tokens) > 10000:
        raise ValueError("Слишком много объектов карты")
    if sorted(layer.position for layer in layers) != list(range(len(layers))):
        raise ValueError("Порядок слоёв должен быть непрерывным")
    layer_ids = {layer.id for layer in layers}
    if any(o.layer_id not in layer_ids for o in objects) or any(
        t.layer_id is not None and t.layer_id not in layer_ids for t in tokens
    ):
        raise ValueError("Слой объекта отсутствует")


@dataclass(frozen=True, slots=True)
class MapDocument:
    title: str
    asset_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    tokens: tuple[TokenInstance, ...] = ()
    grid: MapGrid = field(default_factory=MapGrid)
    layers: tuple[MapLayer, ...] = field(default_factory=lambda: (MapLayer("Слой 1"),))
    objects: tuple[PlacedAssetObject, ...] = ()
    layers_initialized: bool = True
    fog: FogState = field(default_factory=FogState)

    def __post_init__(self):
        validate_id(self.id)
        validate_id(self.asset_id)
        object.__setattr__(self, "title", validate_title(self.title))
        if not isinstance(self.fog, FogState):
            raise ValueError("Invalid map fog")
        if type(self.layers_initialized) is not bool:
            raise ValueError("Invalid layer initialization state")
        validate_map_contents(self.tokens, self.grid, self.layers, self.objects)


@dataclass(frozen=True, slots=True)
class MapPayload:
    asset_id: str
    tokens: tuple = ()
    grid: MapGrid = field(default_factory=MapGrid)
    layers: tuple = field(default_factory=lambda: (MapLayer("Слой 1"),))
    objects: tuple = ()
    layers_initialized: bool = True
    fog: FogState = field(default_factory=FogState)
    version: int = field(default=7, init=False)

    def __post_init__(self):
        validate_id(self.asset_id)
        if not isinstance(self.fog, FogState):
            raise ValueError("Invalid map fog")
        if type(self.layers_initialized) is not bool:
            raise ValueError("Invalid layer initialization state")
        validate_map_contents(self.tokens, self.grid, self.layers, self.objects)
