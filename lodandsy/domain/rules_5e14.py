"""Versioned shipped profile and project overrides over the universal interpreter."""

import math
from dataclasses import dataclass
from functools import lru_cache

from lodandsy.domain.actor_state import VariableValue
from lodandsy.domain.card_schema import (
    ABILITIES,
    ACTOR_TYPES,
    FIELD_DEFINITIONS,
    SKILLS,
    permitted_fields,
)
from lodandsy.domain.equipment import EquipmentFacts
from lodandsy.domain.formula import (
    CalculationError,
    dependency_order,
    evaluate,
    number,
    parse_expression,
)
from lodandsy.domain.modifiers import Modifier, ModifierSource, apply_modifiers


def _proficiency(level):
    if type(level) is not int or not 1 <= level <= 20:
        raise CalculationError("Proficiency поддерживается для уровней 1–20", "unsupported")
    return 2 + (level - 1) // 4


def _class_hp(level, die, gains, constitution):
    if type(level) is not int or level < 1 or level > 20 or die not in (4, 6, 8, 10, 12):
        raise CalculationError("Нужен поддерживаемый класс/уровень/Hit Die", "unsupported")
    if not isinstance(gains, tuple) or len(gains) != level:
        raise CalculationError("Нужна история HP каждого уровня; multiclass — вручную", "unknown")
    if gains[0] != die or any(type(v) is not int or not 1 <= v <= die for v in gains):
        raise CalculationError("Первый уровень: полный Hit Die; проверьте историю HP")
    initial = die + constitution
    if initial < 1:
        raise CalculationError("Особый случай HP первого уровня: выберите manual", "unsupported")
    if any(gain + constitution < 1 for gain in gains[1:]):
        raise CalculationError(
            "Минимальный прирост/изменение CON требует исторических условий; выберите manual",
            "unsupported",
        )
    return initial + sum(max(1, gain + constitution) for gain in gains[1:])


def _select(ability, *modifiers):
    if ability not in ABILITIES:
        raise CalculationError("Выберите характеристику", "unknown")
    return modifiers[ABILITIES.index(ability)]


def _unsupported_hp(level):
    raise CalculationError("Мультикласс: укажите ручное итоговое HP", "unsupported")


def _numeric_function(function):
    def call(*values):
        return number(function(*(number(v) for v in values)))

    return call


def armor_dexterity(category, dexterity):
    dexterity = number(dexterity)
    if category not in {"none", "light", "medium", "heavy"}:
        raise CalculationError("Неизвестная категория надетого доспеха")
    return 0 if category == "heavy" else min(dexterity, 2) if category == "medium" else dexterity


FUNCTIONS = {
    "armor_dexterity": armor_dexterity,
    "floor": _numeric_function(math.floor),
    "ceil": _numeric_function(math.ceil),
    "min": _numeric_function(lambda *values: min(values)),
    "max": _numeric_function(lambda *values: max(values)),
    "proficiency_for_level": _proficiency,
    "class_hp": _class_hp,
    "select": _select,
    "unsupported_hp": _unsupported_hp,
}
for _key, _types in {
    "armor_dexterity": ("text", "number"),
    "floor": ("number",),
    "ceil": ("number",),
    "proficiency_for_level": ("number",),
    "class_hp": ("number", "number", "sequence", "number"),
    "select": ("text", *("number",) * 6),
    "unsupported_hp": ("number",),
}.items():
    FUNCTIONS[_key].argument_types = _types
_MOD_ARGUMENTS = ", ".join(k + "_mod" for k in ABILITIES)
DEFAULT_FORMULAS = {
    **{key: "base_" + key for key in ABILITIES},
    **{key + "_mod": f"floor(({key} - 10) / 2)" for key in ABILITIES},
    "proficiency": "proficiency_for_level(level) if is_character else proficiency_manual",
    "hp_max": "class_hp(level, hit_die, hp_gains, constitution_mod) "
    "if is_character and is_single_class else "
    "unsupported_hp(level) if is_character else base_hp_max",
    "ac": "armor_base + armor_dexterity(armor_type, dexterity_mod)",
    "speed": "speed_base",
    "initiative": "dexterity_mod",
    **{
        key + "_save": f"{key}_mod + (proficiency if {key}_save_proficient else 0)"
        for key in ABILITIES
    },
    **{
        key: f"{ability}_mod + ({key}_proficiency * proficiency if {key}_proficiency > 0 else 0)"
        for key, ability in SKILLS.items()
    },
    "passive_perception": "10 + perception + 5 * perception_advantage",
    "casting_modifier": f"select(casting_ability, {_MOD_ARGUMENTS})",
    "spell_attack": "casting_modifier + proficiency + spell_bonus",
    "spell_dc": "8 + casting_modifier + proficiency + spell_bonus",
    "weapon_attack": f"select(attack_ability, {_MOD_ARGUMENTS}) + "
    "(proficiency if attack_proficient else 0) + attack_bonus",
    "carrying_capacity": "strength * 15",
    "carried_weight": "inventory_weight",
}
INPUT_NAMES = frozenset(
    {key for key, definition in FIELD_DEFINITIONS.items() if definition.scope == "card"}
    | {"base_" + key for key, definition in FIELD_DEFINITIONS.items() if definition.scope == "card"}
    | {
        "is_character",
        "is_single_class",
        "inventory_weight",
        "armor_type",
        "armor_base",
        "shield",
        "base_armor_type",
        "base_armor_base",
        "base_shield",
        "armor_none",
        "armor_light",
        "armor_medium",
    }
)


@dataclass(frozen=True, slots=True)
class ProjectRules:
    ruleset: str = "dnd_5e_2014"
    version: int = 2
    revision: int = 0
    overrides: tuple = ()

    def __post_init__(self):
        if self.ruleset != "dnd_5e_2014" or type(self.version) is not int or self.version != 2:
            raise ValueError("Unsupported ruleset/version")
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("Invalid rules revision")
        if not isinstance(self.overrides, tuple) or len(self.overrides) > len(DEFAULT_FORMULAS):
            raise ValueError("Invalid formula overrides")
        if len(dict(self.overrides)) != len(self.overrides):
            raise ValueError("Duplicate formula target")
        object.__setattr__(self, "overrides", tuple(sorted(self.overrides)))
        compile_rules(self.overrides)


@lru_cache(maxsize=32)
def compile_rules(overrides):
    formulas = dict(DEFAULT_FORMULAS)
    for target, source in overrides:
        if target not in formulas:
            raise ValueError("Неизвестная цель формулы: " + str(target))
        formulas[target] = source
    types = {
        key: {
            "bool": "bool",
            "text": "text",
            "richtext": "text",
            "entity": "text",
            "asset": "text",
            "text_list": "sequence",
            "number_list": "sequence",
            "modifier_list": "sequence",
        }.get(definition.data_type, "number")
        for key, definition in FIELD_DEFINITIONS.items()
        if definition.scope == "card"
    }
    types.update({"base_" + key: value for key, value in tuple(types.items())})
    types.update({key: "number" for key in formulas})
    types.update(
        is_character="bool",
        is_single_class="bool",
        inventory_weight="number",
        armor_type="text",
        armor_base="number",
        shield="bool",
        base_armor_type="text",
        base_armor_base="number",
        base_shield="bool",
        armor_none="text",
        armor_light="text",
        armor_medium="text",
    )
    expressions = {
        key: parse_expression(
            source,
            INPUT_NAMES | formulas.keys(),
            FUNCTIONS,
            name_types=types,
            expected_type="number",
        )
        for key, source in formulas.items()
    }
    for expression in expressions.values():
        if not expression.dependencies:
            evaluate(expression, lambda key: None, FUNCTIONS)
    return expressions, dependency_order(expressions)


@dataclass(frozen=True)
class EffectiveValues:
    values: dict
    automatic: dict
    equipment: EquipmentFacts | None = None
    sources: tuple = ()

    def get(self, key):
        return self.values.get(
            key, VariableValue(status="unsupported", diagnostic="Не поддерживается: " + key)
        )


def calculate(
    card,
    actor=None,
    rules=None,
    *,
    sources=(),
    inventory_weight=None,
    incomplete="",
    equipment=None,
):
    if card.card_type not in ACTOR_TYPES:
        return EffectiveValues(
            {
                key: VariableValue(
                    card.value(key),
                    source="card",
                    status="unknown" if card.value(key) is None else "ok",
                )
                for key in permitted_fields(card.card_type)
            },
            {},
        )
    rules = rules or ProjectRules()
    expressions, order = compile_rules(rules.overrides)
    equipment = equipment if equipment is not None else EquipmentFacts()
    if equipment.shield:
        shield = Modifier(
            "ac", operand=equipment.shield_bonus, id="e71b9ac2-e58a-4984-8d42-7a6766e71b10"
        )
        sources = (
            *sources,
            ModifierSource(
                ("equipment", equipment.shield_item.row_id, equipment.shield_item.item_id),
                shield,
                equipment.shield_item.label,
            ),
        )
    source_map = {}
    for source in sources:
        source_map.setdefault(source.modifier.target, []).append(source)
    inputs = {
        key: card.value(key)
        for key, definition in FIELD_DEFINITIONS.items()
        if definition.scope == "card"
    }
    inputs.update(
        armor_type=equipment.armor_type, armor_base=equipment.armor_base, shield=equipment.shield
    )
    inputs.update({"base_" + key: value for key, value in tuple(inputs.items())})
    inputs.update(
        is_character=card.card_type == "character",
        inventory_weight=inventory_weight,
        is_single_class=card.value("hp_progression") == "single_class",
        armor_none="none",
        armor_light="light",
        armor_medium="medium",
    )
    result, automatic = {}, {}

    def read(key):
        if key in result:
            value = result[key]
            if value.status != "ok":
                raise CalculationError(value.diagnostic, value.status)
            return value.value
        return inputs.get(key)

    for key in order:
        expression = expressions[key]
        dependencies = set(expression.dependencies)
        for dependency in expression.dependencies:
            if dependency in result:
                dependencies.update(result[dependency].dependencies)
        selected_sources = source_map.get(key, ())
        dependencies.update(source.identity for source in selected_sources)
        if key == "ac":
            dependencies.update(
                ("equipment", item.row_id, item.item_id)
                for item in (equipment.armor, equipment.shield_item)
                if item
            )
        dependencies = frozenset(dependencies)
        try:
            if key == "ac" and equipment.diagnostic:
                raise CalculationError(equipment.diagnostic, "incomplete")
            value = evaluate(expression, read, FUNCTIONS)
            if incomplete:
                raise CalculationError(incomplete, "incomplete")
            value = apply_modifiers(value, key, selected_sources)
            if key in {*ABILITIES, "hp_max"} and type(value) is float and value.is_integer():
                value = int(value)
            if key in {*ABILITIES, "hp_max"} and (type(value) is not int or value < 0):
                raise CalculationError("Результат должен быть целым неотрицательным: " + key)
            if key in {"ac", "speed"} and value < 0:
                raise CalculationError("Отрицательное значение: " + key)
            labels = sorted({source.label for source in selected_sources if source.label})
            if key == "ac" and equipment.armor:
                labels = sorted(set(labels) | {equipment.armor.label})
            origin = "formula" + (" · " + ", ".join(labels) if labels else "")
            item = VariableValue(value, "derived", origin, dependencies=dependencies)
        except CalculationError as error:
            item = VariableValue(
                status=error.status, diagnostic=str(error), dependencies=dependencies
            )
        automatic[key] = item
        if key in {"hp_max", "ac", "speed"}:
            override = actor.value(key + "_override") if actor is not None else None
            if override is not None:
                item = VariableValue(override, "present", "actor manual")
            elif card.value(key + "_mode") == "manual":
                value = card.value(key)
                item = VariableValue(
                    value,
                    "null" if value is None else "present",
                    "card manual",
                    "unknown" if value is None else "ok",
                    "Не задано ручное итоговое значение" if value is None else "",
                )
        result[key] = item
    # Declared values stay addressable, without becoming another canonical copy.
    for key in permitted_fields(card.card_type):
        if key not in result:
            value = card.value(key)
            result[key] = VariableValue(
                value, source="card", status="unknown" if value is None else "ok"
            )
    if actor is not None:
        result.update(
            {
                key: VariableValue(value, "present", "actor", "unknown" if value is None else "ok")
                for key, value in actor.values
            }
        )
    return EffectiveValues(result, automatic, equipment, tuple(sources))
