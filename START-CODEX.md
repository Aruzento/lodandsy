# LODANDSY — стабильная база итерации7

1. Прочитать AGENTS.md, docs/MVP.md, ADR-027/030/031/032 и
   docs/validation/2026-11-20-iteration-7-stabilization.md. Итерация7 в целом принята;
   не выполнять пакет A–G заново. Сначала проверить фактический HEAD/working tree/CI.
2. Следующую разработку вести отдельными функциональными модулями от main,
   в рамках текущей задачи Linear и её зависимостей. Cards/Tables/Maps/Dice сохраняют
   независимых владельцев; общие Core/Resources/Media/navigation — узкие контракты.
3. Каждый runtime-файл, включая helpers/presentation/fog, явно классифицирован в
   test_module_boundaries.py. Изменения ownership/существенных контрактов фиксировать
   в ADR и согласовывать, если они не утверждены текущей задачей. Архитектуру не
   перестраивать ради каталогов. SQLite14/Card5/Map6/Table3/UIstate4; legacy нет.
4. Structured drafts: cancel старого owner не меняет чужое новое поколение;
   raw/base/observed/error согласованы, None baseline сохраняется. Autosave/Ctrl+S
   сохраняют только валидный канон, конфликт разрешается явно.
5. Проверять завершённые блоки целевыми пакетами, полный gate после стабилизации.
   Не повторять baseline/full build без изменений и необходимости. Обновлять
   фактические ADR/MVP/Linear/report и draw.io при изменении архитектуры.
6. Git по явному разрешению владельца. Native Qt/offscreen не заменяют физические
   DPI/monitor tests; ARU-64 требует реальной Windows без Python. Публичный release
   и чистая Windows приёмка не следуют автоматически из merge в main.
