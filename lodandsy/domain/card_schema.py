"""Built-in canonical fields and presentation definitions, independent of GUI and storage."""

import math
import re
from dataclasses import dataclass

from lodandsy.domain.module_values import validate_id


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

    def validate(self, value):
        if value is None:
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
        else:
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
    *(
        FieldDefinition(key, label, "number", "character", minimum=0)
        for key, label in [("hp", "HP"), ("ac", "AC"), ("speed", "Скорость")]
    ),
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
    FieldDefinition("mow_id", "Исходный ID MOW", "entity", "source"),
    FieldDefinition("mow_type", "Исходный тип MOW", "text", "source"),
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
            ("race", "class_or_role", "hp", "ac", "speed"),
            "character",
            (
                ("Описание", "rich_text", "description"),
                ("История", "rich_text", None),
                ("Связи", "rich_text", None),
                ("Инвентарь", "table_ref", "inventory"),
                ("Заметки", "rich_text", None),
            ),
        ),
        CardTypeDefinition("item", "Предмет", ("rarity", "weight", "cost")),
        CardTypeDefinition("location", "Локация", ("region", "climate", "danger_level")),
        CardTypeDefinition("folder", "Папка"),
        CardTypeDefinition(
            "creature",
            "Существо",
            ("race", "class_or_role", "hp", "ac", "speed"),
            "character",
            (
                ("Описание", "rich_text", "description"),
                ("История", "rich_text", None),
                ("Связи", "rich_text", None),
                ("Инвентарь", "table_ref", "inventory"),
                ("Заметки", "rich_text", None),
            ),
        ),
        CardTypeDefinition("region", "Регион", ("climate", "danger_level")),
        *(
            CardTypeDefinition(key, label)
            for key, label in [
                ("magic", "Магия"),
                ("skill", "Навык"),
                ("object", "Объект"),
                ("lore", "Лор"),
            ]
        ),
    )
}


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
    else:
        value = text
    definition.validate(value)
    return value


def available_fields(card):
    permitted = {
        *CARD_TYPES[card.card_type].fields,
        "featured",
        "related_entity",
        "token_image",
        "token_kind",
        "token_cells_w",
        "token_cells_h",
    }
    present = dict(card.values)
    return tuple(
        f for f in FIELD_DEFINITIONS.values() if f.key in permitted and f.key not in present
    )
