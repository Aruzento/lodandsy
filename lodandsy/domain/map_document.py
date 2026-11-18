import math
from dataclasses import dataclass, field
from uuid import uuid4

from lodandsy.domain.module_values import validate_id, validate_title


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

    def __post_init__(self):
        validate_id(self.id)
        validate_id(self.asset_id)
        object.__setattr__(self, "title", validate_title(self.title))
        if not isinstance(self.pins, tuple) or not all(isinstance(p, MapPin) for p in self.pins):
            raise ValueError("Invalid map pins")
        if len({p.id for p in self.pins}) != len(self.pins):
            raise ValueError("Duplicate marker ID")
