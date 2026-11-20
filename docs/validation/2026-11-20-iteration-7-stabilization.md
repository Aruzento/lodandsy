# Итерация7 — финальная стабилизация

Владелец принял итерацию7 в целом и поручил ARU-46/78/84 перед объединением с main.
Baseline9e06c0b, существующий CI44800017250; baseline suite не повторялся.
Scope: исправить cancel чужого draft и усилить architecture gate. Новых продуктовых
функций, зависимостей, миграций или архитектурной переделки нет.

## Поведение и затронутые файлы

`application/field_edits.py`, `application/tables_service.py`: два owner A/B начинают
редактирование одного значения; B успешно делает commit(finish=False), A публикует
conflict draft; прежний cancel(B) удалял A. Regression suite до исправления:
12failed/2passed, включая восстановление более старого initial draft/status.

Каждая публикация draft теперь получает session-only token. Cancel сравнивает token
редактора с текущим: при несовпадении завершает только owner, не трогает чужой draft.
Для своего поколения возвращает исходные raw/error/base/copied conflict целиком.
Учитываются same-raw publication, новая observed canonical value, None baseline,
semantic flush, reopen и явные UseSaved/ApplyMine. SQLite14/Card5/Map6/Table3/UIstate4
сохраняются; autosave/Ctrl+S по-прежнему пишут только валидный канон.

`tests/test_module_boundaries.py`, `prototypes/architecture_graph.py`: все88runtime
modules явно назначены Cards/Tables/Maps/Dice/shared/integration. Полный graph186edges,
0cycles. Gate включает helpers/bindings/codecs/presentation/fog, absolute/relative/
from-package alias и imports внутри функций. AST анализ не исполняет приложение.
Проверяются транзитивные пути через shared helpers, domain purity и отсутствие UI
в application services/helpers. Integration allowlist и конкретные разрешённые edges
описаны ADR-027; единственный узкий domain edge CARD_TYPES проверяет конкретный symbol.
Negative fixtures подтверждают, что forbidden imports действительно обнаруживаются.

`tests/test_conflict_resolution.py`: оба сервиса, finishFalse/True, flush, cancel,
old initial draft, third canonical edit, own snapshot restore, nullable baseline.
Native Qt keyboard cases проверяют Ctrl+S→conflict→Escape→blur для Card и обоих
направлений embedded/standalone Table, save/reload и явное решение. Они используют
реальные widgets/delegates; параллельный owner открывается через публичный edit API.

AGENTS/MVP/ADR027/032/README/START-CODEX и build checklist обновлены. Существующая
`docs/architecture/LODANDSY.drawio` соответствует владельцам; граф production
зависимостей не изменился. Следующая разработка — по отдельным модулям от main.

## Фактические проверки

- Targeted Windows batch: `pytest tests/test_conflict_resolution.py
  tests/test_module_boundaries.py tests/test_semantic_input.py tests/test_nonblocking_drafts.py
  tests/test_reference_inventory.py tests/test_save_coordinator.py -q -p no:cacheprovider`:
  **55passed,7.70s**.
- Один итоговый локальный `pytest -q -p no:cacheprovider` с Windows QPA:
  **441passed,1skipped,1warning,74.97s**. Skip — local Windows symlink permission;
  warning — assertion rewriting уже импортированного tests.project_fixture.
- `ruff check .`, `pip check`, `git diff --check` — passed.
- Architecture graph: **88modules/186edges/0cycles**, строгие positive/negative tests passed.

- Production source smoke Windows с NASA233MP — passed.
- Одна locked Windows build после стабилизации: PyInstaller6.22.3,53.66s;
  frozen parity **90modules,0mismatches/0missing/0obsolete**.
- Fresh ZIP extraction в новую кириллическую папку, запуск frozen233MP smoke из TEMP
  с Windows-only PATH, без PYTHONHOME/PYTHONPATH/QT_PLUGIN_PATH — exit0/passed.
  Host имеет Python: это не clean-Windows доказательство.
- Итоговый ZIP повторно проверен: CRC, source manifest/checkout, все130EXE/DLL/PYD
  идентичны свежей распаковке, прошедшей smoke; private references/QtWebEngine отсутствуют.

[Машинные результаты source/frozen/parity/architecture](2026-11-20-iteration7-stabilization-evidence.json).
Сборка: `.prototype-deps/LODANDSY-Iteration7-Stable-2026-11-20.zip`, SHA256 — в соседнем
`.zip.sha256`; checksum не включён внутрь отчёта в ZIP во избежание самоссылки.
280source files включают действующие тесты/инструкции/отчёт и исходную draw.io.
После smoke менялся только текст документации и source bundle, бинарники не менялись.
Локальный полный suite не повторялся для docs. CI выполняет стандартный Windows gate
при push; ссылки на финальный commit/CI и факт объединения фиксируются в ARU-46/78/84.

## Приёмка и ограничения

Общая продуктовая приёмка7 владельца учтена. Нового ручного осмотра физического
второго монитора/mixedDPI и чистой Windows без Python эта доработка не проводила;
ARU-64 остаётся отдельным открытым пунктом. Qt keyboard tests не выдаются за эти проверки.
Full snapshot writer и синхронный backup сохраняют прежние ограничения.
Пользовательские проекты и приватные незакоммиченные вложения не затрагиваются.
Merge/public release — разные действия; публичный release не выполняется.
