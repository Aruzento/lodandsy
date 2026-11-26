import pytest

from lodandsy.application.cards_service import CardsService
from lodandsy.domain.actor_state import ActorRef
from lodandsy.domain.card import Card
from lodandsy.domain.equipment import EquipmentEntry, resolve_equipment
from lodandsy.domain.formula import CalculationError, evaluate, parse_expression
from lodandsy.domain.modifiers import Modifier, ModifierSource, apply_modifiers
from lodandsy.domain.rules_5e14 import FUNCTIONS, ProjectRules, calculate


def warrior(**changes):
    return Card("Warrior", card_type="character").with_fields(
        {
            "level": 5,
            "hit_die": 10,
            "hp_gains": (10, 6, 6, 6, 6),
            "constitution": 14,
            "hp_max_mode": "auto",
            **changes,
        }
    )


@pytest.mark.parametrize("score,result", [(9, -1), (10, 0), (14, 2), (16, 3), (18, 4)])
def test_ability_floor_and_proficiency(score, result):
    assert calculate(warrior(strength=score)).get("strength_mod").value == result
    for level, bonus in [(1, 2), (4, 2), (5, 3), (9, 4), (13, 5), (17, 6), (20, 6)]:
        assert calculate(warrior(level=level)).get("proficiency").value == bonus
    assert calculate(warrior(level=21)).get("proficiency").status == "unsupported"


def test_hp_history_modifiers_manual_armor_skills_and_units():
    card = warrior(
        dexterity=9,
        ac_mode="auto",
        speed_mode="auto",
        perception_proficiency=2,
        wisdom=14,
        casting_ability="wisdom",
    )
    assert calculate(card).get("hp_max").value == 44
    modifier = Modifier("constitution", operand=2)
    sources = (ModifierSource(("actor", "table", "row", modifier.id), modifier),)
    equipment = resolve_equipment(
        (
            EquipmentEntry("armor", "a", "Кираса", "armor", "medium", 14),
            EquipmentEntry("shield", "s", "Щит", "shield"),
        )
    )
    result = calculate(card, sources=sources, equipment=equipment)
    assert result.get("hp_max").value == 49
    assert result.get("ac").value == 15
    assert result.get("perception").value == 8
    assert result.get("passive_perception").value == 18
    assert result.get("spell_dc").value == 13
    assert result.get("spell_attack").value == 5
    assert result.get("speed").value == 30
    assert result.get("carrying_capacity").value == 150
    manual = calculate(card.with_fields({"hp_max": 80, "hp_max_mode": "manual"}), sources=sources)
    assert manual.get("hp_max").value == 80 and manual.automatic["hp_max"].value == 49
    assert calculate(warrior(hp_gains=())).get("hp_max").status == "unknown"
    shield = Modifier("ac", operand=2, group="shield", policy="max")
    doubled = calculate(
        card,
        equipment=resolve_equipment((equipment.armor,)),
        sources=(ModifierSource(("item", shield.id), shield),),
    )
    assert doubled.get("ac").value == 15
    assert calculate(warrior(hp_progression="multiclass")).get("hp_max").status == "unsupported"
    assert (
        calculate(warrior(level=2, constitution=0, hp_gains=(10, 1))).get("hp_max").status
        == "unsupported"
    )


@pytest.mark.parametrize(
    "source",
    [
        "__import__('os')",
        "x.y",
        "x[0]",
        "[x for x in y]",
        "lambda: 1",
        "2 ** 100000",
        "unknown + 1",
        "1" * 4097,
        "+" * 200 + "1",
    ],
)
def test_formula_syntax_and_budgets_are_rejected(source):
    with pytest.raises((ValueError, CalculationError)):
        parse_expression(source, {"x"}, FUNCTIONS)


def test_cycle_division_bool_and_source_stacking():
    with pytest.raises(ValueError, match="Цикл"):
        ProjectRules(overrides=(("strength", "constitution"), ("constitution", "strength")))
    for source in ("1 / 0", "1 + True"):
        with pytest.raises(ValueError):
            expression = parse_expression(source, (), FUNCTIONS)
            evaluate(expression, lambda key: None, FUNCTIONS)
    fixed = Modifier("ac", "set", 18)
    conflict = Modifier("ac", "set", 20)
    with pytest.raises(CalculationError):
        apply_modifiers(
            10,
            "ac",
            (
                ModifierSource(("row1", fixed.id), fixed),
                ModifierSource(("row2", conflict.id), conflict),
            ),
        )
    bonus = Modifier("ac", operand=2, group="shield", policy="max")
    source = ModifierSource(("row", bonus.id), bonus)
    assert apply_modifiers(10, "ac", (source, source)) == 12


def test_atomic_clamp_and_rules_preview_staleness(qapp):
    cards = CardsService()
    card = cards.create_card("HP", card_type="character")
    cards.update_card_fields(card.id, {"hp_max": 100})
    ref = cards.create_actor(card.id)
    cards.update_actor(ref, {"hp_current": 70, "hp_temp": 5})
    cards.update_card_fields(card.id, {"hp_max": 120})
    assert cards.get_actor(ref).value("hp_current") == 70
    events = []
    cards.core.committed.connect(lambda: events.append(1))
    cards.update_card_fields(card.id, {"hp_max": 50})
    assert cards.get_actor(ref).value("hp_current") == 50
    assert cards.get_actor(ref).value("hp_temp") == 5 and events == [1]
    with pytest.raises(ValueError):
        cards.update_actor(ref, {"hp_current": 51})
    cards.update_card_fields(card.id, {"hp_max_mode": "auto"})
    preview = cards.preview_rules((("hp_max", "20"),))
    assert cards.get_actor(ref).value("hp_current") == 50
    cards.apply_rules(preview)
    assert cards.get_actor(ref).value("hp_current") == 20
    with pytest.raises(ValueError):
        cards.apply_rules(preview)
    before = cards.rules
    with pytest.raises(ValueError):
        cards.preview_rules((("hp_max", "1 / 0"),))
    assert cards.rules == before
    assert cards.effective(ActorRef(card.id, ref.actor_id)).get("hp_max").value == 20
