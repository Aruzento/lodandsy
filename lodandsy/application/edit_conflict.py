from dataclasses import dataclass


@dataclass(slots=True)
class EditConflict:
    raw: str
    base: object
    observed: object


class ConcurrentEditError(ValueError):
    def __init__(self, message, base, observed):
        super().__init__(message)
        self.base, self.observed = base, observed
