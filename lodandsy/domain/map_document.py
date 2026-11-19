import math
from dataclasses import dataclass, field
from uuid import uuid4

from lodandsy.domain.module_values import validate_id, validate_title


def _number(value, minimum, maximum, label):
    if (type(value) not in (int, float) or not minimum <= value <= maximum
            or not math.isfinite(value)):
        raise ValueError(f"Некорректное значение: {label}")


@dataclass(frozen=True, slots=True)
class MapGrid:
    enabled: bool = False
    cell_size: float = 64
    offset_x: float = 0
    offset_y: float = 0
    opacity: float = .35
    snap: bool = False

    def __post_init__(self):
        if type(self.enabled) is not bool or type(self.snap) is not bool:
            raise ValueError("Некорректные настройки сетки")
        _number(self.cell_size, 1, 1_000_000, "размер клетки")
        _number(self.offset_x, -1e9, 1e9, "смещение X")
        _number(self.offset_y, -1e9, 1e9, "смещение Y")
        _number(self.opacity, 0, 1, "прозрачность")

    def snap_point(self, x, y):
        return tuple(offset + (math.floor((point - offset) / self.cell_size) + .5)
                     * self.cell_size for point, offset in [(x, self.offset_x), (y, self.offset_y)])


@dataclass(frozen=True, slots=True)
class MapToken:
    title: str
    asset_id: str
    x: float
    y: float
    width: float = 64
    height: float = 64
    z: int = 0
    id: str = field(default_factory=lambda: str(uuid4()))
    card_id: str | None = None

    def __post_init__(self):
        validate_id(self.id)
        validate_id(self.asset_id)
        if self.card_id is not None:
            validate_id(self.card_id)
        object.__setattr__(self, "title", validate_title(self.title))
        for value, label in [(self.x, "X"), (self.y, "Y")]:
            _number(value, 0, 1e9, label)
        for value in (self.width, self.height):
            _number(value, 1, 1_000_000, "размер токена")
        if type(self.z) is not int or not 0 <= self.z <= 10000:
            raise ValueError("Некорректный порядок токена")


@dataclass(frozen=True, slots=True)
class MapPin:
    title: str
    x: float
    y: float
    id: str = field(default_factory=lambda: str(uuid4()))
    card_id: str | None = None

    def __post_init__(self):
        validate_id(self.id)
        if self.card_id is not None:
            validate_id(self.card_id)
        object.__setattr__(self, "title", validate_title(self.title))
        for value in (self.x, self.y):
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not 0 <= value <= 1):
                raise ValueError("Координаты маркера должны быть в пределах карты")


@dataclass(frozen=True, slots=True)
class MapDocument:
    title: str
    asset_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    pins: tuple[MapPin, ...] = ()
    tokens: tuple[MapToken, ...] = ()
    grid: MapGrid = field(default_factory=MapGrid)

    def __post_init__(self):
        validate_id(self.id)
        validate_id(self.asset_id)
        object.__setattr__(self, "title", validate_title(self.title))
        if not isinstance(self.pins, tuple) or not all(isinstance(p, MapPin) for p in self.pins):
            raise ValueError("Invalid map pins")
        if len({p.id for p in self.pins}) != len(self.pins):
            raise ValueError("Duplicate marker ID")
        if (not isinstance(self.tokens, tuple)
                or not all(isinstance(token, MapToken) for token in self.tokens)
                or not isinstance(self.grid, MapGrid)):
            raise ValueError("Invalid map tokens/grid")
        ids = [item.id for item in (*self.pins, *self.tokens)]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate map object ID")
