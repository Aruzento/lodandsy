# LODANDSY — Cards / Actors / 5e14 после итерации7

1. Прочитать AGENTS.md, docs/MVP.md, ADR-027/030/031/032/033/034 и
   docs/validation/2026-11-20-iteration-7-stabilization.md. Итерация7 в целом принята;
   не выполнять пакет A–G заново. Сначала проверить фактический HEAD/working tree/CI.
2. Следующую разработку вести отдельными функциональными модулями от main,
   в рамках текущей задачи Linear и её зависимостей. Cards/Tables/Maps/Dice сохраняют
   независимых владельцев; общие Core/Resources/Media/navigation — узкие контракты.
3. Каждый runtime-файл, включая helpers/presentation/fog, явно классифицирован в
   test_module_boundaries.py. Изменения ownership/существенных контрактов фиксировать
   в ADR и согласовывать, если они не утверждены текущей задачей. Архитектуру не
   перестраивать ради каталогов. SQLite16/Card7/Map9/Actor1/Rules1(profile2)/Table3/UIstate4; legacy нет.
4. Structured drafts: cancel старого owner не меняет чужое новое поколение;
   raw/base/observed/error согласованы, None baseline сохраняется. Autosave/Ctrl+S
   сохраняют только валидный канон, конфликт разрешается явно.
5. Проверять завершённые блоки целевыми пакетами, полный gate после стабилизации.
   Не повторять baseline/full build без изменений и необходимости. Обновлять
   фактические ADR/MVP/Linear/report и draw.io при изменении архитектуры.
6. Git по явному разрешению владельца. Native Qt/offscreen не заменяют физические
   DPI/monitor tests; ARU-64 требует реальной Windows без Python. Публичный release
   и чистая Windows приёмка не следуют автоматически из merge в main.

7. Пакет Cards/Actors/Variables/5e14 утверждён владельцем 21.11.2026. Card owns Actor,
   не Entity registry; индивидуальные inventory обычные Table, Token содержит refs.
   Pure rules/evaluator относятся к Cards, Core settings opaque. Generic mutations
   проходят тот же итоговый валидатор. Formula preview связан с revision+serial;
   HP clamp атомарен. Guarded placement Undo не откатывает последующие HP/inventory.
   Итоги и физические ограничения: docs/validation/2026-11-21-cards-actors-5e14.md.
8. Исправление непройденной UI-приёмки A–F: docs/validation/2026-11-21-ui-acceptance-fix.md.
   Игровые поля в системных страницах Card Editor, Item modifiers — отдельная native форма,
   Inspector Card технический, Actor/Map оперативный. Правила открываются из gear справа.
   Виртуальные keys разрешены в UIstate4, не являются UUID Section; формат мира не изменён.
   Git-действия этим запросом не разрешены. ARU-65/80/83 остаются В работе до ручной приёмки.


Дополнение 22.11.2026 — лист персонажа v2 / ADR-035: inline ability scores, 3/2/1
блоки с 18skills/6saves, homebrew race/class/subclass/level. Item equipment facts
определяются только active inventory rows, один armor/shield с atomic replace/cancel.
Card armor_type/armor_base/shield удалены; это только resolved formula inputs.
SQLite16/Card7, профиль5e14 version2; legacy/миграции отсутствуют по новому прямому
решению владельца «все миры тестовые». SQLite15 отклоняется без записи/удаления.
Ручной итоговый AC побеждает, оборудование и источники видны в native AC dialog.
Отчёт: docs/validation/2026-11-22-character-sheet-v2.md. Новые Git-публикации не разрешены.

Maps M5: ADR-036 и docs/validation/2026-11-25-map-m5.md. Предыдущая принятая
полировка сохранена в текущем checkout; Git-интеграция/CI проверяются по фактическим
refs. Map8 добавляет shapes/portals, Map7 читается без записи. Не возвращать hidden
transient coordinates в Player ради старых тестовых ожиданий.


Maps M5.5 / ARU-91 (25.11.2026): ADR-037, единый MapToolState на игровой MapView,
native vertical QAction toolbar / last-shape menu / context / overflow. V/H/B/E/M
только на canvas, Space временно включает руку, Escape отменяет локальный жест.
Успешное создание shape/portal возвращает выбор; brush/eraser сохраняют режим.
Формат SQLite16/Card7/Map8 и канон/Undo/презентация M5 сохранены. M5 e40a25d принят
владельцем82/82, включая чистую Windows. Новая панель ждёт отдельной ручной приёмки;
ARU-91 не закрывать. Отчёт: docs/validation/2026-11-25-map-m55.md. Commit/push/merge
этим заданием не разрешены. Кандидат: LODANDSY-Map-M5.5-2026-11-25.zip.


Дополнение 26.11.2026 — финальная полировка M5.5 / ARU-91, ARU-89:
иконки18px/stroke1.15 при кнопках36px, выбор/вершины одной группой, измерения только
в настройках сетки; новый map получает5ft/cell, старые калибровки не меняются.
Редактор карты — справа с текстом, native flyout gap10 logical px с screen bounds,
тонкие разделители групп. ADR-038: Map9 добавляет strict boolean portal.hide_label;
Map7/8 читаются без записи с hide_label=false. SQLite16/Card7/UIstate4 прежние.
Подпись хранится при скрытии; навигация/иконка и Map Undo сохранены. Новая поставка:
LODANDSY-Map-M5.5-Final-2026-11-26.zip; отчёт docs/validation/2026-11-26-map-m55-final.md.
Обе задачи остаются In Progress до ручной приёмки; commit/push/merge не разрешены.
