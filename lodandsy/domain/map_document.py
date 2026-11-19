import math
from dataclasses import dataclass, field
from uuid import uuid4

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
    opacity: float = 0.65
    snap: bool = False
    color: str = "#ffffff"

    def __post_init__(self):
        if type(self.enabled) is not bool or type(self.snap) is not bool:
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

    def snap_point(self, x, y, cells_w=1, cells_h=1):
        # Center anchor; align the footprint's upper-left corner to cell boundaries.
        return tuple(
            offset
            + (math.floor((point - offset) / self.cell_size - cells / 2 + 0.5) + cells / 2)
            * self.cell_size
            for point, offset, cells in [(x, self.offset_x, cells_w), (y, self.offset_y, cells_h)]
        )


@dataclass(frozen=True, slots=True)
class MapToken:
    title: str
    asset_id: str | None
    x: float
    y: float
    cells_w: int = 1
    cells_h: int = 1
    z: int = 0
    id: str = field(default_factory=lambda: str(uuid4()))
    entity_id: str | None = None
    kind: str = "character"

    def __post_init__(self):
        validate_id(self.id)
        if self.asset_id is not None:
            validate_id(self.asset_id)
        if self.entity_id is not None:
            validate_id(self.entity_id)
        if self.kind not in {"character", "item"}:
            raise ValueError("Некорректный тип токена")
        object.__setattr__(self, "title", validate_title(self.title))
        for value, label in [(self.x, "X"), (self.y, "Y")]:
            _number(value, 0, 1e9, label)
        for value in (self.cells_w, self.cells_h):
            if type(value) is not int or not 1 <= value <= 100:
                raise ValueError("Footprint must contain 1..100 cells")
        if type(self.z) is not int or not 0 <= self.z <= 10000:
            raise ValueError("Некорректный порядок токена")


@dataclass(frozen=True, slots=True)
class MapDocument:
    title: str
    asset_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    tokens: tuple[MapToken, ...] = ()
    grid: MapGrid = field(default_factory=MapGrid)

    def __post_init__(self):
        validate_id(self.id)
        validate_id(self.asset_id)
        object.__setattr__(self, "title", validate_title(self.title))
        if (
            not isinstance(self.tokens, tuple)
            or not all(isinstance(token, MapToken) for token in self.tokens)
            or not isinstance(self.grid, MapGrid)
        ):
            raise ValueError("Invalid map tokens/grid")
        ids = [item.id for item in self.tokens]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate map object ID")


@dataclass(frozen=True, slots=True)
class MapPayload:
    asset_id: str
    tokens: tuple = ()
    grid: MapGrid = field(default_factory=MapGrid)
    version: int = field(default=3, init=False)
