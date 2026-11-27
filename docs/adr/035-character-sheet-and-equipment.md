# ADR-035 — компактный лист и единственный источник экипировки

22.11.2026, ARU-65/80/83. Задание LODANDSY_character_sheet_v2.md. Baseline
fee0106e6fc9177db3438332d83a3cd46a75d4a7/codex/ui-acceptance-fix, CI44950034132 success.
Владелец подтвердил: все миры тестовые, legacy разрешено вырезать. Вопрос о переносе
закрыт: миграций/конвертации нет; старые файлы не переписываются и не удаляются.

## Данные и совместимость

Описанные здесь правила несовместимости относятся к прежним прототипам.
С v0.01 применяется [ADR-040](040-managed-projects-v001.md).

Новый формат SQLite16/Card7; Map7/Actor1/Table3/UIstate4 сохранены. Rules payload1,
профиль dnd_5e_2014 version2. Старые schema15/Card6/profile1 явно отклоняются до записи.
Это новое разрешение относится к текущим тестовым мирам, а не вывод из отказа schema14.

Удалены Card fields armor_type/armor_base/shield и искусственный shield source из Card.
Item имеет equipment_kind=item/armor/shield, armor_category=light/medium/heavy,
armor_ac и nullable shield_bonus (None означает профильные +2; zero сохраняется).
Применимость по Card type и общая type validation охватывают constructor/service/
generic replacement/load. Неполное определение доспеха разрешено редактировать, но
active incomplete Item не превращается в «без брони»; auto AC имеет диагностику.

Единственный признак активности — existing active cell UUID строки обычной Table.
Шаблонный inventory теперь создаётся с active=false, его колонки/строки копируются
по действующему UUID remap в owned Actor inventory. Чтение не создаёт Table или Actor.
Изменения Item наследуются; копий его фактов в Actor нет. Qty не множит броню/щит/бонус.
Missing Item остаётся soft ref и даёт incomplete, manual final остаётся приоритетным.

Pure EquipmentEntry/EquipmentFacts/resolve_equipment принадлежат Cards, без Qt/SQL.
Integration inventory_inputs разрешает ссылки/строки и передаёт facts+ModifierSources
чистому calculate. Финальный validate_project проверяет template и owned контексты:
два active armor или shield отвергаются при любом mutation/load, не выбирается первый.
Обычный template Table можно структурно изменить: повреждённая схема даёт incomplete
inputs, не ложный unarmored AC. Owned inventory сохраняет строгие descriptors.

ProjectActions.set_inventory_activity заменяет выбранную категорию одной транзакцией
с generation+state serial и expected Table. GUI спрашивает replace/cancel; generic API
не открывает диалог и отвергает конфликт. Tables получает generic cell command/caption
hooks из composition root, не импортирует game rules/Equipment UI. Scalar Undo остаётся
вне пакета; существующий addressed placement Undo не откатывает новое состояние.

## Правила

Resolved armor_type/armor_base/shield и base_ имена остаются typed read-only formula
inputs; это не FieldDefinition saved values. Старого второго канона/alias writer нет.
Basic Rules2014: unarmored10+DEX, light base+DEX, medium base+min(DEX,2), heavy base;
один active shield (стандарт+2), затем прежние modifier stages. Отрицательная DEX
не обнуляется. Safe AST/DAG/budgets/preview guards не ослаблены. AC formula задаёт
основу и DEX; shield и дополнительные источники идут после неё. У новой Card AC по умолчанию auto; manual выбирается явно. Manual Card/Actor
AC — окончательный итог, auto доступен для справки. Старый профиль1 не загружается;
в профиле2 сохранены безопасные имена входов, unknown/invalid формула отвергается.

EffectiveValues несёт readonly facts/sources; addressed derived notifications учитывают
изменения provenance даже при равном числовом результате. base_effective_changed
обновляет лист без Actor при изменении Item/template; Actor events сохраняются.
Нет broad editor reset, EventBus, отдельного registry или дополнительного writer.

## Native UI

3/2/1 ability blocks: крупный modifier, inline score, первая строка save, затем skills
в русском алфавитном порядке. ○/●/◆ имеют accessible names и дают0/1/2; saves bool.
Actor score read-only effective, base origin по tooltip/при отличии, явное «К базе».
Все изменения используют прежние FieldEdits/ValueAddress/owner generation/expected value.

Header race/class/subclass/level с native editable suggestions, unknown/homebrew.
Class change фильтрует подсказки архетипа, но не стирает существующий несовместимый
выбор: показывает уведомление. Каталог подсказок не выдаёт классовых/расовых бонусов.
Ресурсы компактны; один AC indicator открывает native breakdown/manual dialog.
Доспех/категория/база/DEX/щит/прочие modifiers read-only, переход в inventory явный.
HP/speed details по нажатию; прочие настройки/атаки/магия/нагрузка доступны ниже.
Технический Card Inspector, оперативный Map Inspector и native rich text сохранены.

Новых зависимостей нет. Полный gate и сборка после targeted стабилизации; физическую
приёмку не подменять QWidget.grab/offscreen. Commit/push/merge/release не разрешены.
