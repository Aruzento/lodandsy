"""Typed modifier sources; activation/ownership belongs to the caller."""

import re
from dataclasses import dataclass, field
from uuid import uuid4

from lodandsy.domain.formula import CalculationError, number
from lodandsy.domain.module_values import validate_id


@dataclass(frozen=True, slots=True)
class Modifier:
    target: str
    operation: str = "add"
    operand: float = 0
    group: str = ""
    policy: str = "sum"
    priority: int = 0
    condition: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self):
        validate_id(self.id)
        if not isinstance(self.target, str) or not re.fullmatch(
            r"[a-z][a-z0-9_]{0,63}", self.target
        ):
            raise ValueError("Invalid modifier target")
        if self.operation not in {"add", "set", "multiply", "minimum", "maximum"}:
            raise ValueError("Invalid modifier operation")
        number(self.operand)
        if self.policy not in {"sum", "max", "unique"}:
            raise ValueError("Invalid stacking policy")
        if type(self.priority) is not int or abs(self.priority) > 10000:
            raise ValueError("Invalid modifier priority")
        if not isinstance(self.group, str) or len(self.group) > 64:
            raise ValueError("Invalid stacking group")
        if not isinstance(self.condition, str) or len(self.condition) > 256:
            raise ValueError("Invalid modifier condition")


@dataclass(frozen=True, slots=True)
class ModifierSource:
    identity: tuple
    modifier: Modifier
    label: str = ""


def apply_modifiers(value, target, sources):
    unique, groups = {}, {}
    for source in sources:
        modifier = source.modifier
        if modifier.target != target:
            continue
        previous = unique.get(source.identity)
        if previous is not None and previous != modifier:
            raise CalculationError("Конфликт identity источника")
        unique[source.identity] = modifier
    for identity, modifier in unique.items():
        if modifier.condition:
            raise CalculationError(
                "Условие предмета требует ручного подтверждения/поддержки", "unsupported"
            )
        key = (modifier.group or identity, modifier.operation)
        groups.setdefault(key, []).append(modifier)
    selected = []
    for entries in groups.values():
        policies = {m.policy for m in entries}
        if len(policies) != 1:
            raise CalculationError("Конфликт правил совмещения")
        policy = entries[0].policy
        if policy == "unique" and len(entries) > 1:
            raise CalculationError("Источники не могут совмещаться")
        selected.extend([max(entries, key=lambda m: m.operand)] if policy == "max" else entries)
    sets = [m for m in selected if m.operation == "set"]
    if sets:
        priority = max(m.priority for m in sets)
        operands = {m.operand for m in sets if m.priority == priority}
        if len(operands) != 1:
            raise CalculationError("Конфликт альтернативных значений равного приоритета")
        value = operands.pop()
    for operation in ("multiply", "add", "minimum", "maximum"):
        for modifier in sorted(selected, key=lambda m: m.id):
            if modifier.operation != operation:
                continue
            operand = modifier.operand
            value = {
                "multiply": lambda: value * operand,
                "add": lambda: value + operand,
                "minimum": lambda: max(value, operand),
                "maximum": lambda: min(value, operand),
            }[operation]()
            number(value)
    return number(value)
