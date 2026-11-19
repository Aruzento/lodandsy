from dataclasses import dataclass
from random import SystemRandom

FACES = (4, 6, 8, 10, 12, 20, 100)


@dataclass(frozen=True, slots=True)
class DiceConfig:
    counts: tuple[int, ...] = (0, 0, 0, 0, 0, 1, 0)
    modifier: int = 0

    def __post_init__(self):
        if (
            not isinstance(self.counts, tuple)
            or len(self.counts) != len(FACES)
            or any(type(n) is not int or not 0 <= n <= 1000 for n in self.counts)
            or sum(self.counts) > 1000
        ):
            raise ValueError("Допустимо суммарно до 1000 кубиков; количество неотрицательно")
        if type(self.modifier) is not int or abs(self.modifier) > 1_000_000_000:
            raise ValueError("Модификатор должен быть целым, |K| ≤ 1000000000")

    def expression(self):
        terms = [f"{n}d{faces}" for n, faces in zip(self.counts, FACES) if n]
        return " + ".join(terms or ["0"]) + (f" {self.modifier:+d}" if self.modifier else "")


@dataclass(frozen=True, slots=True)
class DiceResult:
    groups: tuple
    modifier: int

    @property
    def total(self):
        return sum(sum(values) for _, values in self.groups) + self.modifier

    def text(self):
        groups = "\n".join(
            f"d{faces}: {', '.join(map(str, values))} (Σ {sum(values)})"
            for faces, values in self.groups
        )
        return f"{groups}\nМодификатор: {self.modifier:+d}\nИтог = {self.total}"


def roll_dice(config: DiceConfig, rng=None):
    if not isinstance(config, DiceConfig):
        raise ValueError("Ожидается конфигурация кубиков")
    if not sum(config.counts):
        raise ValueError("Выберите хотя бы один кубик")
    rng = rng if rng is not None else SystemRandom()
    groups = tuple(
        (faces, tuple(rng.randint(1, faces) for _ in range(count)))
        for faces, count in zip(FACES, config.counts)
        if count
    )
    return DiceResult(groups, config.modifier)
