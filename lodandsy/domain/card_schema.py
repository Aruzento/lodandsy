"""Built-in canonical fields and presentation definitions, independent of GUI and storage."""

import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache

from lodandsy.domain.modifiers import Modifier
from lodandsy.domain.module_values import validate_id

ACTOR_TYPES = frozenset({"character", "creature", "object"})
ABILITIES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")
SKILLS = {
    "athletics": "strength",
    "acrobatics": "dexterity",
    "sleight_of_hand": "dexterity",
    "stealth": "dexterity",
    "arcana": "intelligence",
    "history": "intelligence",
    "investigation": "intelligence",
    "nature": "intelligence",
    "religion": "intelligence",
    "animal_handling": "wisdom",
    "insight": "wisdom",
    "medicine": "wisdom",
    "perception": "wisdom",
    "survival": "wisdom",
    "deception": "charisma",
    "intimidation": "charisma",
    "performance": "charisma",
    "persuasion": "charisma",
}


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    key: str
    label: str
    data_type: str = "text"
    group: str = "general"
    default: object = None
    minimum: float = -1e9
    maximum: float = 1e9
    max_length: int = 2000
    hint: str = ""
    integer: bool = False
    scope: str = "card"
    nullable: bool = True
    unit: str = ""
    choices: tuple = ()
    origin: str = "system"

    def validate(self, value):
        if value is None:
            if not self.nullable:
                raise ValueError(f"«{self.label}»: значение обязательно")
            return
        kind = self.data_type
        if kind in {"text", "richtext"}:
            valid = isinstance(value, str) and "\0" not in value and len(value) <= self.max_length
        elif kind == "number":
            valid = (
                type(value) in (int, float)
                and math.isfinite(value)
                and self.minimum <= value <= self.maximum
                and (not self.integer or type(value) is int)
            )
        elif kind == "bool":
            valid = type(value) is bool
        elif kind == "text_list":
            valid = (
                isinstance(value, tuple)
                and len(value) <= 64
                and all(
                    isinstance(v, str) and v.strip() and "\0" not in v and len(v) <= 128
                    for v in value
                )
                and len(set(value)) == len(value)
            )
        elif kind in {"entity", "asset"}:
            validate_id(value)
            valid = True
        elif kind == "number_list":
            valid = (
                isinstance(value, tuple)
                and len(value) <= 100
                and all(type(v) is int and self.minimum <= v <= self.maximum for v in value)
            )
        elif kind == "modifier_list":
            valid = (
                isinstance(value, tuple)
                and len(value) <= 64
                and all(isinstance(v, Modifier) for v in value)
                and len({v.id for v in value}) == len(value)
            )
        else:
            valid = False
        if self.choices and value not in self.choices:
            valid = False
        if not valid:
            raise ValueError(f"Некорректное поле «{self.label}» ({kind})")


@dataclass(frozen=True, slots=True)
class CardTypeDefinition:
    id: str
    title: str
    fields: tuple[str, ...] = ()
    token_kind: str = "item"
    initial_sections: tuple = ()


_FIELDS = (
    FieldDefinition("title", "Название", max_length=2000),
    FieldDefinition("summary", "Краткое описание", max_length=500),
    FieldDefinition("description", "Описание", "richtext", max_length=2**21),
    FieldDefinition("aliases", "Также известен как", "text_list", default=()),
    FieldDefinition("featured", "Важная карточка", "bool"),
    FieldDefinition("race", "Раса", "text", "character"),
    FieldDefinition("class_or_role", "Класс / роль", "text", "character"),
    FieldDefinition("subclass", "Архетип", "text", "character"),
    *(
        FieldDefinition(key, label, "number", "character", minimum=0)
        for key, label in [("ac", "AC"), ("speed", "Скорость")]
    ),
    FieldDefinition(
        "equipment_kind",
        "Категория экипировки",
        "text",
        "item",
        default="item",
        nullable=False,
        choices=("item", "armor", "shield"),
    ),
    FieldDefinition(
        "armor_category", "Категория доспеха", "text", "item", choices=("light", "medium", "heavy")
    ),
    FieldDefinition("armor_ac", "Базовый КД доспеха", "number", "item", minimum=0),
    FieldDefinition("shield_bonus", "Бонус щита (пусто: +2)", "number", "item", minimum=0),
    FieldDefinition("rarity", "Редкость", "text", "item"),
    FieldDefinition("weight", "Вес", "number", "item", minimum=0),
    FieldDefinition("cost", "Стоимость", "number", "item", minimum=0),
    FieldDefinition("region", "Регион", "text", "location"),
    FieldDefinition("climate", "Климат", "text", "location"),
    FieldDefinition("danger_level", "Опасность", "number", "location", minimum=0),
    FieldDefinition("related_entity", "Связанный документ", "entity", "links"),
    FieldDefinition("token_image", "Изображение токена", "asset", "presentation"),
    FieldDefinition("token_kind", "Вид токена", "text", "presentation", hint="character / item"),
    *(
        FieldDefinition(
            key, label, "number", "presentation", default=1, minimum=1, maximum=100, integer=True
        )
        for key, label in [
            ("token_cells_w", "Ширина токена (клетки)"),
            ("token_cells_h", "Высота токена (клетки)"),
        ]
    ),
    FieldDefinition("player", "Игрок", "bool", "identity", default=False, nullable=False),
    FieldDefinition(
        "level",
        "Уровень",
        "number",
        "character",
        default=1,
        minimum=1,
        integer=True,
        nullable=False,
    ),
    FieldDefinition(
        "xp", "Опыт", "number", "character", default=0, minimum=0, integer=True, nullable=False
    ),
    *(
        FieldDefinition(
            k, label, "number", "abilities", default=10, minimum=0, integer=True, nullable=False
        )
        for k, label in zip(
            ABILITIES, ("Сила", "Ловкость", "Телосложение", "Интеллект", "Мудрость", "Харизма")
        )
    ),
    FieldDefinition("hp_max", "HP максимум", "number", "resources", minimum=0, integer=True),
    FieldDefinition(
        "hp_current", "HP текущее", "number", "resources", minimum=0, integer=True, scope="actor"
    ),
    FieldDefinition(
        "hp_temp",
        "HP временное",
        "number",
        "resources",
        default=0,
        minimum=0,
        integer=True,
        scope="actor",
        nullable=False,
    ),
    *(
        FieldDefinition(
            k + "_override",
            label + " — индивидуальное итоговое",
            "number",
            "resources",
            minimum=0,
            integer=k == "hp_max",
            scope="actor",
        )
        for k, label in (("hp_max", "HP"), ("ac", "AC"), ("speed", "Скорость (ft)"))
    ),
    FieldDefinition(
        "proficiency_manual",
        "Бонус мастерства существа",
        "number",
        "character",
        minimum=0,
        integer=True,
    ),
    FieldDefinition(
        "modifiers", "Модификаторы предмета", "modifier_list", "item", default=(), nullable=False
    ),
    *(
        FieldDefinition(
            k + "_mode",
            label + " — режим",
            "text",
            "calculation",
            default="auto" if k == "ac" else "manual",
            nullable=False,
            choices=("auto", "manual"),
        )
        for k, label in (("hp_max", "HP"), ("ac", "AC"), ("speed", "Скорость"))
    ),
    FieldDefinition(
        "hit_die",
        "Кость класса",
        "number",
        "hp_inputs",
        minimum=4,
        maximum=12,
        integer=True,
        choices=(4, 6, 8, 10, 12),
    ),
    FieldDefinition(
        "hp_gains",
        "Прирост HP по уровням (через запятую)",
        "number_list",
        "hp_inputs",
        default=(),
        minimum=1,
        maximum=12,
        nullable=False,
    ),
    FieldDefinition(
        "hp_progression",
        "Прогрессия HP",
        "text",
        "hp_inputs",
        default="single_class",
        nullable=False,
        choices=("single_class", "multiclass"),
    ),
    FieldDefinition(
        "speed_base",
        "Базовая скорость (ft)",
        "number",
        "movement",
        default=30,
        minimum=0,
        unit="ft",
    ),
    FieldDefinition(
        "casting_ability", "Характеристика заклинаний", "text", "spell", choices=ABILITIES
    ),
    FieldDefinition(
        "attack_ability",
        "Характеристика атаки",
        "text",
        "attack",
        default="strength",
        nullable=False,
        choices=ABILITIES,
    ),
    FieldDefinition(
        "attack_proficient", "Владение атакой", "bool", "attack", default=False, nullable=False
    ),
    FieldDefinition(
        "attack_bonus", "Дополнительный бонус атаки", "number", "attack", default=0, nullable=False
    ),
    FieldDefinition(
        "spell_bonus", "Дополнительный бонус магии", "number", "spell", default=0, nullable=False
    ),
    FieldDefinition(
        "perception_advantage",
        "Пассивное восприятие: -1/0/1",
        "number",
        "skills",
        default=0,
        integer=True,
        choices=(-1, 0, 1),
        nullable=False,
    ),
    *(
        FieldDefinition(
            k + "_save_proficient",
            k + " — владение спасброском",
            "bool",
            "saves",
            default=False,
            nullable=False,
        )
        for k in ABILITIES
    ),
    *(
        FieldDefinition(
            k + "_proficiency",
            k + " — владение (0/1/2)",
            "number",
            "skills",
            default=0,
            integer=True,
            choices=(0, 1, 2),
            nullable=False,
        )
        for k in SKILLS
    ),
)
FIELD_DEFINITIONS = {f.key: f for f in _FIELDS}
CARD_TYPES = {
    t.id: t
    for t in (
        CardTypeDefinition("note", "Заметка"),
        CardTypeDefinition("article", "Статья"),
        CardTypeDefinition(
            "character",
            "Персонаж",
            ("race", "class_or_role", "hp_max", "ac", "speed"),
            "character",
            (
                ("Описание", "rich_text", "description"),
                ("История", "rich_text", None),
                ("Связи", "rich_text", "relations"),
                ("Инвентарь", "table_ref", "inventory"),
                ("Заметки", "rich_text", None),
            ),
        ),
        CardTypeDefinition(
            "item",
            "Предмет",
            (
                "rarity",
                "weight",
                "cost",
                "modifiers",
                "equipment_kind",
                "armor_category",
                "armor_ac",
                "shield_bonus",
            ),
        ),
        CardTypeDefinition("location", "Локация", ("region", "climate", "danger_level")),
        CardTypeDefinition("folder", "Папка"),
        CardTypeDefinition(
            "creature",
            "Существо",
            ("race", "class_or_role", "hp_max", "ac", "speed"),
            "character",
            (
                ("Описание", "rich_text", "description"),
                ("История", "rich_text", None),
                ("Связи", "rich_text", "relations"),
                ("Инвентарь", "table_ref", "inventory"),
                ("Заметки", "rich_text", None),
            ),
        ),
        CardTypeDefinition("region", "Регион", ("climate", "danger_level")),
        CardTypeDefinition(
            "object",
            "Объект",
            ("hp_max", "ac", "speed"),
            "item",
            (
                ("Описание", "rich_text", "description"),
                ("Связи", "rich_text", "relations"),
                ("Инвентарь", "table_ref", "inventory"),
            ),
        ),
        *(
            CardTypeDefinition(key, label)
            for key, label in [
                ("magic", "Магия"),
                ("skill", "Навык"),
                ("lore", "Лор"),
            ]
        ),
    )
}

GAME_FIELDS = frozenset(
    f.key
    for f in _FIELDS
    if f.group
    in {
        "identity",
        "abilities",
        "resources",
        "calculation",
        "hp_inputs",
        "character",
        "defence",
        "movement",
        "spell",
        "attack",
        "skills",
        "saves",
    }
)


@lru_cache(maxsize=64)
def permitted_fields(card_type, scope="card"):
    permitted = {
        "title",
        "summary",
        "description",
        "aliases",
        "featured",
        "related_entity",
        "token_image",
        "token_kind",
        "token_cells_w",
        "token_cells_h",
        *CARD_TYPES[card_type].fields,
    }
    if card_type in ACTOR_TYPES:
        permitted |= GAME_FIELDS
    if card_type == "object":
        permitted -= {
            f.key
            for f in _FIELDS
            if f.group
            in {
                "character",
                "hp_inputs",
                "spell",
                "attack",
                "skills",
                "saves",
            }
        }
        permitted |= {"hp_max", "ac", "speed"}
    return frozenset(k for k in permitted if FIELD_DEFINITIONS[k].scope == scope)


def validate_fields(card_type, values, scope="card"):
    keys = set()
    for key, value in values:
        definition = field_definition(key)
        if key in keys or key not in permitted_fields(card_type, scope):
            raise ValueError(f"Поле {key} недоступно для {card_type}/{scope}")
        definition.validate(value)
        keys.add(key)


def field_definition(key):
    key = "title" if key == "name" else key
    if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", key):
        raise ValueError("Некорректный ключ поля")
    try:
        return FIELD_DEFINITIONS[key]
    except KeyError:
        raise ValueError(f"Неизвестное поле: {key}") from None


def parse_field(key, text):
    definition = field_definition(key)
    kind = definition.data_type
    if text == "" and kind not in {"text", "richtext", "text_list"}:
        value = None
    elif kind == "number":
        try:
            value = int(text) if definition.integer else float(text)
        except ValueError, TypeError:
            raise ValueError(f"«{definition.label}»: введите число") from None
    elif kind == "text_list":
        value = tuple(dict.fromkeys(p.strip() for p in text.split(",") if p.strip()))
    elif kind == "number_list":
        try:
            value = tuple(int(p.strip()) for p in text.split(",") if p.strip())
        except ValueError:
            raise ValueError("Введите целые числа через запятую") from None
    elif kind == "bool":
        if str(text).casefold() not in {"true", "false", "1", "0", "да", "нет"}:
            raise ValueError("Введите true/false")
        value = str(text).casefold() in {"true", "1", "да"}
    elif kind == "modifier_list":
        if len(text.encode("utf-8")) > 65536:
            raise ValueError("Слишком большой список модификаторов")
        try:
            data = json.loads(text)
            if not isinstance(data, list):
                raise ValueError("Ожидается список модификаторов")
            value = tuple(Modifier(**entry) for entry in data)
        except (TypeError, json.JSONDecodeError, RecursionError) as error:
            raise ValueError("Некорректный список модификаторов") from error
    else:
        value = text
    definition.validate(value)
    return value


def available_fields(card):
    permitted = permitted_fields(card.card_type) - {"title", "description", "summary", "aliases"}
    present = dict(card.values)
    return tuple(
        f for f in FIELD_DEFINITIONS.values() if f.key in permitted and f.key not in present
    )
