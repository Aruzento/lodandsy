import re
from dataclasses import dataclass, field
from random import SystemRandom
from uuid import uuid4

from lodandsy.domain.module_values import validate_id, validate_title

_DICE = re.compile(r"([0-9]*)[dDдД]([0-9]+)([+-][0-9]+)?", re.ASCII)


@dataclass(frozen=True, slots=True)
class DiceResult:
    expression: str
    dice: tuple[int, ...]
    modifier: int

    @property
    def total(self):
        return sum(self.dice) + self.modifier

    def text(self):
        modifier = f" {self.modifier:+d}" if self.modifier else ""
        return f"{self.expression}: [{', '.join(map(str, self.dice))}]{modifier} = {self.total}"


def roll_dice(expression: str, rng=None):
    if not isinstance(expression, str) or len(expression) > 80:
        raise ValueError("Введите выражение NdM±K, например 2d6+3")
    match = _DICE.fullmatch(expression.strip().replace(" ", ""))
    if not match:
        raise ValueError("Введите выражение NdM±K, например 2d6+3")
    count, faces, modifier = int(match[1] or 1), int(match[2]), int(match[3] or 0)
    if not 1 <= count <= 1000 or not 2 <= faces <= 1_000_000 or abs(modifier) > 1_000_000_000:
        raise ValueError("Допустимо 1–1000 кубиков, 2–1000000 граней, |K| ≤ 1000000000")
    rng = rng or SystemRandom()
    return DiceResult(f"{count}d{faces}" + (f"{modifier:+d}" if modifier else ""),
                      tuple(rng.randint(1, faces) for _ in range(count)), modifier)


@dataclass(frozen=True, slots=True)
class RandomTable:
    title: str
    id: str = field(default_factory=lambda: str(uuid4()))
    rows: tuple[str, ...] = ()

    def __post_init__(self):
        validate_id(self.id)
        object.__setattr__(self, "title", validate_title(self.title))
        if (not isinstance(self.rows, tuple) or
                not all(isinstance(row, str) and "\0" not in row for row in self.rows)):
            raise ValueError("Invalid table rows")

    def choose(self, rng=None):
        choices = [(i + 1, row) for i, row in enumerate(self.rows) if row.strip()]
        if not choices:
            raise ValueError("Добавьте хотя бы одну непустую строку")
        return (rng or SystemRandom()).choice(choices)
