"""Russian presentation catalog; canonical identifiers and definitions stay unchanged."""

import re

from lodandsy.domain.card_schema import ABILITIES, FIELD_DEFINITIONS, SKILLS

ATTRIBUTES_PAGE = "system:attributes"
MODIFIERS_PAGE = "system:modifiers"
SYSTEM_PAGES = frozenset({ATTRIBUTES_PAGE, MODIFIERS_PAGE})


def system_pages(card_type):
    if card_type in {"character", "creature", "object"}:
        return ((ATTRIBUTES_PAGE, "Характеристики"),)
    if card_type == "item":
        return ((MODIFIERS_PAGE, "Модификаторы"),)
    return ()


ABILITY_NAMES = dict(
    zip(ABILITIES, ("Сила", "Ловкость", "Телосложение", "Интеллект", "Мудрость", "Харизма"))
)
ABILITY_SHORT = dict(zip(ABILITIES, ("СИЛ", "ЛОВ", "ТЕЛ", "ИНТ", "МДР", "ХАР")))
SKILL_NAMES = dict(
    zip(
        SKILLS,
        (
            "Атлетика",
            "Акробатика",
            "Ловкость рук",
            "Скрытность",
            "Магия",
            "История",
            "Расследование",
            "Природа",
            "Религия",
            "Уход за животными",
            "Проницательность",
            "Медицина",
            "Восприятие",
            "Выживание",
            "Обман",
            "Запугивание",
            "Выступление",
            "Убеждение",
        ),
    )
)
LABELS = {
    **ABILITY_NAMES,
    **SKILL_NAMES,
    "ac": "Класс Доспеха (КД)",
    "hp_max": "Максимум хитов",
    "hp_current": "Текущие хиты",
    "hp_temp": "Временные хиты",
    "hp_max_override": "Личный максимум хитов",
    "ac_override": "Личный КД",
    "speed_override": "Личная скорость, фт.",
    "speed": "Скорость, фт.",
    "speed_base": "Базовая скорость, фт.",
    "hp_max_mode": "Расчёт максимума",
    "ac_mode": "Расчёт КД",
    "speed_mode": "Расчёт скорости",
    "hp_gains": "Прирост хитов по уровням",
    "hit_die": "Кость хитов класса",
    "hp_progression": "Прогрессия хитов",
    "armor_type": "Вид брони",
    "armor_base": "КД брони",
    "proficiency": "Бонус мастерства",
    "proficiency_manual": "Бонус мастерства существа",
    "initiative": "Инициатива",
    "passive_perception": "Пассивное Восприятие",
    "casting_modifier": "Модификатор заклинаний",
    "spell_attack": "Атака заклинанием",
    "spell_dc": "Сложность спасброска заклинания",
    "weapon_attack": "Бонус атаки",
    "carrying_capacity": "Грузоподъёмность, фн.",
    "carried_weight": "Вес инвентаря, фн.",
    "inventory_weight": "Вес инвентаря, фн.",
    "weight": "Вес, фн.",
    "perception_advantage": "Пассивное Восприятие",
    "is_character": "Персонаж",
    "is_single_class": "Один класс",
    "actor_name": "Имя участника",
}
ABILITY_GENITIVE = dict(
    zip(ABILITIES, ("Силы", "Ловкости", "Телосложения", "Интеллекта", "Мудрости", "Харизмы"))
)
LABELS.update({a + "_mod": "Модификатор " + n for a, n in ABILITY_GENITIVE.items()})
LABELS.update({a + "_save": "Спасбросок · " + n for a, n in ABILITY_NAMES.items()})
LABELS.update({a + "_save_proficient": n for a, n in ABILITY_NAMES.items()})
LABELS.update({s + "_proficiency": n for s, n in SKILL_NAMES.items()})
CHOICES = {
    "auto": "Автоматически",
    "manual": "Вручную — итоговое",
    "single_class": "Один класс",
    "multiclass": "Мультикласс — вручную",
    "none": "Без брони",
    "light": "Лёгкая",
    "medium": "Средняя",
    "heavy": "Тяжёлая",
    "add": "Прибавить",
    "set": "Установить",
    "multiply": "Умножить",
    "minimum": "Не ниже",
    "maximum": "Не выше",
    "sum": "Суммирование",
    "max": "Наибольший бонус",
    "unique": "Единственный источник",
    **ABILITY_NAMES,
}
STATUSES = {
    "ok": "Рассчитано",
    "unknown": "Не задано",
    "unsupported": "Не поддерживается",
    "incomplete": "Неполные данные",
    "error": "Ошибка расчёта",
}
TECHNICAL_GROUPS = frozenset({"general", "links", "presentation"})


def field_label(key):
    if key.startswith("base_"):
        return "База · " + field_label(key[5:])
    return LABELS.get(key, FIELD_DEFINITIONS[key].label if key in FIELD_DEFINITIONS else key)


def choice_label(key, value):
    if key.endswith("_proficiency"):
        return {0: "Нет владения", 1: "Владение", 2: "Компетентность"}.get(value, str(value))
    if key == "perception_advantage":
        return {-1: "С помехой (−5)", 0: "Обычное", 1: "С преимуществом (+5)"}[value]
    if key == "hit_die":
        return f"к{value}"
    return CHOICES.get(value, str(value))


def field_surface(key):
    definition = FIELD_DEFINITIONS[key]
    if key in {"title", "summary", "description"}:
        return "document"
    if key == "aliases":
        return "data-only"  # Existing resolver metadata, deliberately absent from editors.
    if key == "modifiers":
        return "modifiers"
    if definition.group in TECHNICAL_GROUPS:
        return "inspector"
    if definition.group in {"item", "location"}:
        return "item" if definition.group == "item" else "inspector"
    return "attributes"


def signed(value):
    if value is None:
        return "—"
    return f"+{value:g}" if value >= 0 else f"−{abs(value):g}"


def value_text(value, *, sign=False):
    if value.status != "ok":
        return STATUSES.get(value.status, "Нет результата")
    return signed(value.value) if sign else str(value.value)


def source_text(source):
    prefix, separator, detail = source.partition(" · ")
    prefix = {
        "actor manual": "Ручное значение участника",
        "card manual": "Ручное значение карточки",
        "formula": "Расчёт",
        "default": "По умолчанию",
        "actor": "Участник",
        "card": "Карточка",
    }.get(prefix, prefix)
    return prefix + separator + detail


def error_text(error):
    text = str(error)
    translations = {
        "Proficiency": "Бонус мастерства",
        "Hit Die": "кость хитов",
        "multiclass": "мультикласс",
        "manual": "ручной режим",
        "single_class": "один класс",
        "Invalid modifier target": "Недопустимая цель модификатора",
        "Invalid modifier operation": "Недопустимая операция модификатора",
        "Invalid stacking policy": "Недопустимый способ совмещения",
        "Invalid modifier priority": "Недопустимый приоритет модификатора",
        "Invalid stacking group": "Недопустимая группа совмещения",
        "Invalid modifier condition": "Недопустимое условие модификатора",
        "Unsupported modifier": "Неподдерживаемый модификатор",
        "Unknown entity id": "Документ не найден",
        "Unknown Actor": "Участник не найден",
        "bool": "логическое значение",
        "number": "число",
        "text": "текст",
    }
    for old, new in translations.items():
        text = text.replace(old, new)
    for key, definition in FIELD_DEFINITIONS.items():
        text = text.replace("«" + definition.label + "»", "«" + field_label(key) + "»")
    for key in sorted(LABELS, key=len, reverse=True):
        text = re.sub(r"(?<![a-z_])" + re.escape(key) + r"(?![a-z_])", LABELS[key], text)
    return text.replace("HP", "хитов").replace("CON", "Телосложения").replace("AC", "КД")
