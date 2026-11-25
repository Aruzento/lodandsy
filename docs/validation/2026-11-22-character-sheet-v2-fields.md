# Поля листа v2 — 22.11.2026

Единый FIELD_DEFINITIONS; UI labels не меняют IDs. Armor facts не сохранённые Card fields.

| ID | Название | Тип / scope | UI | Применимость |
|---|---|---|---|---|
| `title` | Название | text/card | document | note, article, character, item, location, folder, creature, region, object, magic, skill, lore |
| `summary` | Краткое описание | text/card | document | note, article, character, item, location, folder, creature, region, object, magic, skill, lore |
| `description` | Описание | richtext/card | document | note, article, character, item, location, folder, creature, region, object, magic, skill, lore |
| `aliases` | Также известен как | text_list/card | data-only | note, article, character, item, location, folder, creature, region, object, magic, skill, lore |
| `featured` | Важная карточка | bool/card | inspector | note, article, character, item, location, folder, creature, region, object, magic, skill, lore |
| `race` | Раса | text/card | attributes | character, creature |
| `class_or_role` | Класс / роль | text/card | attributes | character, creature |
| `subclass` | Архетип | text/card | attributes | character, creature |
| `ac` | Класс Доспеха (КД) | number/card | attributes | character, creature, object |
| `speed` | Скорость, фт. | number/card | attributes | character, creature, object |
| `equipment_kind` | Категория экипировки | text/card | item | item |
| `armor_category` | Категория доспеха | text/card | item | item |
| `armor_ac` | Базовый КД доспеха | number/card | item | item |
| `shield_bonus` | Бонус щита (пусто: +2) | number/card | item | item |
| `rarity` | Редкость | text/card | item | item |
| `weight` | Вес, фн. | number/card | item | item |
| `cost` | Стоимость | number/card | item | item |
| `region` | Регион | text/card | inspector | location |
| `climate` | Климат | text/card | inspector | location, region |
| `danger_level` | Опасность | number/card | inspector | location, region |
| `related_entity` | Связанный документ | entity/card | inspector | note, article, character, item, location, folder, creature, region, object, magic, skill, lore |
| `token_image` | Изображение токена | asset/card | inspector | note, article, character, item, location, folder, creature, region, object, magic, skill, lore |
| `token_kind` | Вид токена | text/card | inspector | note, article, character, item, location, folder, creature, region, object, magic, skill, lore |
| `token_cells_w` | Ширина токена (клетки) | number/card | inspector | note, article, character, item, location, folder, creature, region, object, magic, skill, lore |
| `token_cells_h` | Высота токена (клетки) | number/card | inspector | note, article, character, item, location, folder, creature, region, object, magic, skill, lore |
| `player` | Игрок | bool/card | attributes | character, creature |
| `level` | Уровень | number/card | attributes | character, creature |
| `xp` | Опыт | number/card | attributes | character, creature |
| `strength` | Сила | number/card | attributes | character, creature, object |
| `dexterity` | Ловкость | number/card | attributes | character, creature, object |
| `constitution` | Телосложение | number/card | attributes | character, creature, object |
| `intelligence` | Интеллект | number/card | attributes | character, creature, object |
| `wisdom` | Мудрость | number/card | attributes | character, creature, object |
| `charisma` | Харизма | number/card | attributes | character, creature, object |
| `hp_max` | Максимум хитов | number/card | attributes | character, creature, object |
| `hp_current` | Текущие хиты | number/actor | attributes | character, creature, object |
| `hp_temp` | Временные хиты | number/actor | attributes | character, creature, object |
| `hp_max_override` | Личный максимум хитов | number/actor | attributes | character, creature, object |
| `ac_override` | Личный КД | number/actor | attributes | character, creature, object |
| `speed_override` | Личная скорость, фт. | number/actor | attributes | character, creature, object |
| `proficiency_manual` | Бонус мастерства существа | number/card | attributes | character, creature |
| `modifiers` | Модификаторы предмета | modifier_list/card | modifiers | item |
| `hp_max_mode` | Расчёт максимума | text/card | attributes | character, creature, object |
| `ac_mode` | Расчёт КД | text/card | attributes | character, creature, object |
| `speed_mode` | Расчёт скорости | text/card | attributes | character, creature, object |
| `hit_die` | Кость хитов класса | number/card | attributes | character, creature |
| `hp_gains` | Прирост хитов по уровням | number_list/card | attributes | character, creature |
| `hp_progression` | Прогрессия хитов | text/card | attributes | character, creature |
| `speed_base` | Базовая скорость, фт. | number/card | attributes | character, creature, object |
| `casting_ability` | Характеристика заклинаний | text/card | attributes | character, creature |
| `attack_ability` | Характеристика атаки | text/card | attributes | character, creature |
| `attack_proficient` | Владение атакой | bool/card | attributes | character, creature |
| `attack_bonus` | Дополнительный бонус атаки | number/card | attributes | character, creature |
| `spell_bonus` | Дополнительный бонус магии | number/card | attributes | character, creature |
| `perception_advantage` | Пассивное Восприятие | number/card | attributes | character, creature |
| `strength_save_proficient` | Сила | bool/card | attributes | character, creature |
| `dexterity_save_proficient` | Ловкость | bool/card | attributes | character, creature |
| `constitution_save_proficient` | Телосложение | bool/card | attributes | character, creature |
| `intelligence_save_proficient` | Интеллект | bool/card | attributes | character, creature |
| `wisdom_save_proficient` | Мудрость | bool/card | attributes | character, creature |
| `charisma_save_proficient` | Харизма | bool/card | attributes | character, creature |
| `athletics_proficiency` | Атлетика | number/card | attributes | character, creature |
| `acrobatics_proficiency` | Акробатика | number/card | attributes | character, creature |
| `sleight_of_hand_proficiency` | Ловкость рук | number/card | attributes | character, creature |
| `stealth_proficiency` | Скрытность | number/card | attributes | character, creature |
| `arcana_proficiency` | Магия | number/card | attributes | character, creature |
| `history_proficiency` | История | number/card | attributes | character, creature |
| `investigation_proficiency` | Анализ | number/card | attributes | character, creature |
| `nature_proficiency` | Природа | number/card | attributes | character, creature |
| `religion_proficiency` | Религия | number/card | attributes | character, creature |
| `animal_handling_proficiency` | Уход за животными | number/card | attributes | character, creature |
| `insight_proficiency` | Проницательность | number/card | attributes | character, creature |
| `medicine_proficiency` | Медицина | number/card | attributes | character, creature |
| `perception_proficiency` | Восприятие | number/card | attributes | character, creature |
| `survival_proficiency` | Выживание | number/card | attributes | character, creature |
| `deception_proficiency` | Обман | number/card | attributes | character, creature |
| `intimidation_proficiency` | Запугивание | number/card | attributes | character, creature |
| `performance_proficiency` | Выступление | number/card | attributes | character, creature |
| `persuasion_proficiency` | Убеждение | number/card | attributes | character, creature |

Всего 79 полей / 12 типов. `subclass` — text/character; metadata supports homebrew. Item equipment definitions неполные допускаются, active incomplete не даёт валидный auto AC. `aliases` сохраняет прежний data-only статус. Object.player запрещён прежним application contract.

armor_type/armor_base/shield и их base_ варианты доступны только как resolved formula inputs. Нет ValueAddress writer для этих ключей. Nullable armor_ac/category показывают диагностику до заполнения, nullable shield_bonus означает профильные+2; zero сохраняется.
