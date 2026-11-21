# Cards / Actors / Variables / 5e14 — инженерный отчёт

21.11.2026. Пакет A–I, ARU-65/80/83; architecture gate ARU-84.
Это отчёт об инженерной реализации; физическая приёмка новой сборки отдельно.

## Исходное состояние и полномочия

Проверены checkout main, HEAD и origin/main:
`751b6999a7e42c3dfb70e1dc1d620598f0d9cc0a`. GitHub main совпадал и повторно
проверен перед Git-финализацией. CI44810679827 success: native442/offscreen43.
Полный совпадающий baseline не повторялся. Стабилизация итерации7 принята,
ARU-46/78/84 Done; пакет A–G итерации7 заново не выполнялся.

Входной архив SHA256:
`f7d55bf3d141b99a114776b1e5a0cd079991f911e7c9fd74ccdfe62bc5769bf6`.
Прочитаны 00_START_HERE, 01_REQUIREMENTS, 02_ARCHITECTURE, 03_RULESET_5E14,
04_IMPLEMENTATION_AND_TESTS, 05_CODEX_PROMPT; manifest9/9 проверен. Распаковка
только ignored `.prototype-deps/implementation_5e14`. Инструкции архива применены
в границах прямого запроса владельца, исторические references/PDF — контекст.
Прямой запрос заменил первоначальное ограничение «только аудит»: реализация A–I
разрешена, все продуктовые решения согласованы. Последнее указание владельца
явно разрешает commit/push/merge после доработки и тестов; release не разрешён.

Исходно tracked изменений не было. Сохранены `.codex-remote-attachments/`,
предыдущий untracked architecture audit, личные DOCX/PNG references. Пользовательские
миры, личные файлы и вложения не удалялись, не мигрировались. Они не относятся к
исходникам пакета и не должны попасть в Git/release. Отдельные disposable миры и
изолированные QSettings использовались в проверках, каталог владельца не менялся.

## Источники и принятые уточнения

Изучены AGENTS.md, START-CODEX.md, README.md, docs/MVP.md; ADR-004/014/019–023/
027–032; validation iteration7 и iteration7-stabilization; архитектурный draw.io;
актуальные Linear65/80/83/84 (21.11). Существенные изменения закреплены **до кода**
в ADR-033, далее ADR дополнен фактическими инженерными деталями.

Исследованы domain/card_schema.py, card.py, card_collection.py, entity.py,
document_payloads.py, map_document.py, table_document.py; application/cards_service.py,
field_edits.py, entity_session.py, project_actions.py, tables_service.py, maps_service.py,
codecs, sqlite_project_store.py, project_controller.py, save_coordinator.py;
Card/Inspector/Map/Table UI и tests/test_module_boundaries.py. Новые runtime helpers
имеют явного владельца. Dependencies/стек не менялись.

Расхождения разрешены по утверждённому пакету: прежнее hp заменено hp_max без alias;
read-only audit proposals о shared NPC copy, unset scores, current>max, отложенных
формулах/inventory отменены; SQLite14/Card5/Map6 больше не текущий формат.
Native Card Editor layout, Qt rich document, immutable type, section UUID/Undo,
semantic draft conflicts, Core/SaveCoordinator/Player guards сохранены.

Технические решения без отдельного нового продуктового решения: Actor внутри
CardPayload, normalized DB tables, ValueAddress, final manual override, bounded AST,
4096 sources/2048 derived cache/32 compiled rules, snapshot validation proof, адресные
placement receipts. Они конкретизируют 02_ARCHITECTURE; их ограничения в ADR-033.

## Реализация A–I и соответствие решениям

|Блок / решения|Результат / основные файлы|Целевая проверка|
|---|---|---|
|A, D1–D10/11.1–11.7|Baseline/Linear/archive, новый ADR-033 до runtime.|HEAD/CI/manifest подтверждены.|
|B, R04/R05|Одна applicability/scope/type policy, presence/default/null/0/false; Card constructors/service/generic/load, hp удалён; card_schema/card/actor_state.|38 passed initial B.|
|C, D1/D2/D4/D7,11.3|Cards-owned immutable Actor/default/name/refs, base inheritance; no Entity kind/registry; cards_service/document_payloads.|23 passed initial C.|
|D, D9,11.2/11.6/11.7|Pure formula.py, rules_5e14.py, safe AST/types/DAG, modifiers.py; manual/auto, HP clamp, project overrides.|34 passed C/D/security/architecture; golden/error/preview.|
|E, D10,11.4/11.5|Tables clone template with fresh row/col UUID, owned inventories, active rows, live Item modifiers/cost/description; no quantity bonus multiplier.|34 passed E/D/C/architecture; isolated Object/Actor inventories.|
|F, D8|SQLite15/Card6/Map7/Actor1/Rules1; normalized actors/default/token/rules, composite FK, snapshot/backup.|71 passed F; injected SQL failure/retry/schema14 byte preservation.|
|G, D3/D5/D6,11.1/11.3|ProjectActions placements/copy, Player policy; guarded addressed Undo, maps_service component deltas.|19 passed G; stale creation inverse blocked before index.|
|H, D7/D9/D10|Inspector Card/Actor/Item, names/effective/auto/provenance, relations roster/navigation, active inventory, player dialog, separate rules editor.|60 and69 passed H/regressions, later38 targeted; final preview/delete coverage27 passed.|
|I|ADR/MVP/README/START/AGENTS, draw.io/AST, full gates/source/frozen/package, report/Linear/Git.|Фактические итоговые результаты ниже.|

## Канон, владельцы и API

Card definition/base → immutable ActorState(name,state,inventory) → Token(card+actor ref).
Cards owns variables/rules/state. Tables owns ordinary rows/cells. Maps owns placement,
Map Undo, rendering/fog; получает публичный participant DTO и адресованные callbacks.
ProjectActions объединяет зависимости; EntitySession/EntityCollection — единственная
atomic boundary, opaque settings без D&D в Core. Один SQLite snapshot writer,
post-commit events и отдельный durable revision ACK.

`read_value(ValueAddress)` возвращает presence/source/status; `read_effective(ActorRef,
field_id)` — effective value/diagnostic/dependencies; `update_values(owner,patch,
expected_values)` использует общий путь. `create_actor/get_actor/list_actors`,
`set_player`, `preview_rules/apply_rules/preview_effects`; ProjectActions
`place_card/copy_token/actor_inventory/actor_placements/delete_actor`.
Нет копий base level/HPmax в Token, вычисленные результаты в SQLite не записываются.

Player обычное новое размещение/copy использует default Actor; toggle выбирает
existing/new, старые refs не переписывает. NPC/Object новый/copy — новый UUID,
current=effective max или null, temp0, template inventory с новыми UUID. Map/token/layer
удаление сохраняет Actor/inventory; confirmed Actor/Card delete — каскад hard refs.
Card deletion preview перечисляет participant names/count/inventory count и число
placements; длинные списки компактно ограничены20 с полным количеством. Никакого
автоматического merge/GC. Неожиданный hard ref — отказ, Item soft ref — диагностика.

Undo move не содержит HP/inventory/rules. Creation receipt возвращает те же UUID,
проверяет subsequent edits/refs до QUndoStack index; failed inverse ничего не меняет.
Scalar/delete Undo и перенос NPC между картами не заявлены. Старые drafts очищаются
адресно только для удалённого Actor, после commit; чужой новый draft сохраняется.

## Покрытие правил 5e 2014

Реализованы scores(default10)/floor modifiers, level/XP, proficiency1–20/manual,
шесть saves,18skills с proficiency/expertise, passive Perception±5, initiative,
scalar weapon attack/casting ability/spell attack/DC, armor none/light/medium/heavy
с negative DEX и одним shield, speed ft→m/cells при известном масштабе, carrying
STR×15lb Small/Medium и carried weight. Item modifiers имеют UUID,target, operation,
operand, group/policy/priority; source=(Actor,Table,row,modifier), source labels и
зависимости доступны. Qty влияет на вес, не множит bonus. Manual HP/AC/speed —
окончательное итоговое значение, auto preview сохраняется отдельно.

HP auto требует сохранённой single-class истории: полный first die, затем fixed/rolled
inputs, без reroll при reopen. Warrior5 d10 gains10,6,6,6,6 CON14→44, active+2CON→49.
Multiclass, minimum-edge история (gain+CON<1) явно unsupported/manual; отсутствующая
история unknown. Это честная граница, не приближённая «официальная» формула.
CR proficiency auto, class features, slots capacity/remaining, remaining Hit Dice,
other sizes/movement, armor condition penalties, attunement/concentration/effects,
combat/actions/damage/healing/death/rest не автоматизированы. Пустой UI ресурсов
не выдаётся за работающую механику. Пользовательские definitions и другие rulesets позже.

Официальные материалы: [SRD5.1 CC BY4.0](https://media.wizards.com/2023/downloads/dnd/SRD_CC_v5.1.pdf),
[Using Ability Scores 2014](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/using-ability-scores),
[Classes 2014](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/classes),
[Advancement 2014](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/step-by-step-characters).
Источники сверены при разработке. Формулы — собственная реализация, не полный текст книг;
атрибуция SRD включена build_support/SRD-5.1-NOTICE.txt и LICENSES поставки.

## Проверки T01–T29

|ID|Доказательство|Статус/предел|
|---|---|---|
|T01|test_actor_identity, snapshot Card with empty actors, codec roundtrips|Автоматически; Card не требует размещения.|
|T02|test_actor_placements + source/frozen two maps/shared Actor|Автоматически; native physical sync/caret отдельно.|
|T03|test_actor_identity десять NPC + base level; T27 тысячи|Автоматически.|
|T04|test_actor_inventory Object two owned inventories|Автоматически.|
|T05|test_actor_placements NPC7→copy20, player reuse; smoke|Автоматически.|
|T06|identity set_player on/off + inspector Cancel/dialog|Автоматически по API/Cancel; физический выбор existing/new отдельно.|
|T07|placement deletion/state retention; existing map/layer regressions; relations|Автоматически, физический roster отдельно.|
|T08|inventory explicit owner delete/cascade, delete preview names/counts, Card cascade|Автоматически; подтверждение/destructive UX физически отдельно.|
|T09|test_rules_5e14 atomic clamp/growth/temp/unknown/zero|Автоматически, один committed.|
|T10|test_variable_policy, existing Card fields/codec/security|Автоматически, generic path не обход.|
|T11|inventory activation CON14→16/mod2→3/HP44→49, independent actor|Автоматически.|
|T12|rules manual effective/automatic, UI final overrides|Автоматически; physical ручной режим отдельно.|
|T13|formula syntax/budget/type/cycle/zero/unknown tests|Автоматически; AST не выполняется.|
|T14|rules preview/apply/reset/stale + editor tests|Автоматически; changed results/Actor names/clamps shown.|
|T15|qty8/nonmultiplication, modifier source dedup/shield group|Автоматически.|
|T16|active deleted Item soft ref retained, incomplete|Автоматически; inactive не даёт bonus.|
|T17|identity owner/global UUID/hardref, malformed SQLite load|Автоматически до publication/write.|
|T18|aggregate normalized snapshot, reopen/backup/restore equality; smoke|Автоматически; manual/rules/activity included.|
|T19|schema14 byte-for-byte safe refusal|Автоматически, мигратора нет.|
|T20|SQL trigger abort after actor write before token; dirty/error/retry|Автоматически, durable ACK guard сохранён.|
|T21|placement/copy/move receipt, HP edit blocks unsafe inverse, sameIDs redo|Автоматически, index unchanged.|
|T22|component delta grid/fog vs foreign placement deletion|Автоматически, no resurrection.|
|T23|Actor native Enter/conflict/reopen/UseSaved; existing semantic/escape/flush tests|Автоматически; physical focus/IME/DPI отдельно.|
|T24|Rules draft/preview/stale, core generation closes editor, smoke|Автоматически; physical window UX отдельно.|
|T25|Полный suite existing Card/Map/Table/security/presentation/editor|Автоматически; неизменный native layout.|
|T26|test_module_boundaries + actual AST96/220/0|Автоматически, нет новых запрещённых связей.|
|T27|prototypes/actors_profile.py + three committed JSON reports|Измерено ниже, не SLA.|
|T28|Source/frozen parity/smoke/portable ZIP|Автоматически; clean Windows/physical не выполнены.|
|T29|test_rules_5e14 golden cases + explicit unsupported/unknown|Автоматически в documented coverage.|

## Итоговые команды и результаты

Все команды Python фактически выполнялись через
`.prototype-deps/locked-venv/Scripts/python.exe` (CPython3.14.8 x64),
а не системный python3.13 без pytest. QT_QPA_PLATFORM=windows для native suite.

|Команда / среда|Фактический результат|
|---|---|
|python -m pytest -q -p no:cacheprovider (windows)|476 passed,1 skipped,93.30s. Skip: account cannot create symlink.|
|python -m pytest test_map_fog/test_conflict_resolution/test_project_catalogue (offscreen)|43 passed,4.01s;1 fixture assert-rewrite warning, не runtime warning.|
|python -m ruff check .|All checks passed.|
|python -m pip check|No broken requirements found.|
|git diff --check|Exit0; только Windows LF→CRLF informational notices для нетронутых файлов.|
|python -m prototypes.architecture_graph --report docs/architecture/imports-cards5e14.json|96modules/220edges/0cycles.|
|build_windows.ps1 -Python locked-venv -SkipPackage|Exit0, PyInstaller clean build CPython3.14.8.|
|python -m build_support.verify_frozen|98 compiled modules,0missing/0mismatches/0obsolete.|
|python -m build_support.windows_smoke --large-map-image nasa-blue-marble.jpg|passed=true/windows/source,233MP,backup/restore/layout/actors/rules/Item active.|
|После focus fix, source small smoke|Exit0/passed=true на окончательном драйвере; не замена physical checks.|


Первый общий прогон выявил устаревшие invalid hardref fixtures/mock tuple и реальный
дефект missing template inventory (выбрасывался exception при допустимом relink).
Fixtures приведены к strict contract, missing template выдаёт incomplete;62 targeted
passed. QAction teardown lifecycle исправлен после G targeted; safe bound closure.
Frozen smoke выявил гонку focus в драйвере после закрытия formula dialog: теперь
драйвер ждёт visible/active/native focus перед Table edit. Это не ослабление Table
семантики. Сборка/проверки повторены после необходимых изменений, старый failed
результат не выдан за новый pass.

## Производительность T27

Нативное окно, одинаковая1200×800 карта,1000 placements,20 edits+processEvents.
Baseline импортируется из read-only git archive751b699 в ignored папку;
тот же драйвер/машина/стек. Старый baseline выражает global Card.hp, независимых Actor
там нет: сравнение общего случая не доказывает эквивалентность новой модели.
Token item identity сохраняется во всех режимах, broad scene reset не найден.

|Режим|Actors/Tables|Edit+render p50/p95 ms|Save/Load/Reopen-map ms|Peak/working MiB|
|---|---|---|---|---|
|Baseline global Card.hp|0/0|94.05/100.28|41.49/9.80/264.54|119.66/117.25|
|Новый общий Actor|1/1|75.16/83.17|71.34/17.20/359.25|119.67/119.66|
|1000 independent|1000/1000|148.95/165.31|2547.58/1009.70/3495.91|180.89/177.41|

Общий Actor:20 адресных actor events на20 изменений. Independent:19, первая запись
совпадала с каноном и корректно была no-op. Setup одного outer transaction:0.36s shared,
20.47s independent; производство интерактивных1000 созданий не выдаётся за мгновенное.
Full snapshot writer/линейный обход акторов видны в save/load/edit стоимости. Это
обоснованное ограничение текущей архитектуры, не повод вводить второй канон/ORM.
Измерения включают event dispatch/render request, не физическое время scan-out,
и не заменяют визуальную плавность233MP/двух мониторов. JSON рядом с отчётом.

## Поставка, физическая приёмка и Linear

Windows portable: `.prototype-deps/LODANDSY-Cards-Actors-5e14-2026-11-21.zip`,
рядом `.zip.sha256` и внешний manifest/handoff с точными размером/SHA/Git refs.
EXE/source parity98/98 passed. Финальный frozen self-test на233MP NASA:
passed=true, frozen=true, platform=windows, Unicode/layout/backup/restore/actors/
inventory/rules/Player fog. Машина имеет Python; это не clean-Windows результат.
Свежая Unicode распаковка: Exit0/passed=true с Windows-only PATH, без PYTHONHOME/
PYTHONPATH/Qt plugin env, cwdTEMP; квитанция рядом с ZIP. CRC и307 source hashes
совпали с checkout, EXE идентичен проверенному. После обновления отчёта пакет
перепакован и исходники/EXE повторно сверены, runtime не изменялся.
Source bundle содержит manifest SHA256 исходников, лицензии Qt/ADS/Python/libvips/SRD;
private references/attachments/cache/worlds и прежний untracked audit исключены.
Исторические validation reports не переписаны как новые результаты.


ARU-65/80/83: пакет реализован, результаты добавляются в существующие задачи; не Done
до обязательной приёмки. ARU-84 Done не переоткрывался: architecture gate сохранён.
ARU-64 остаётся In Progress — новой Windows без установленного Python нет.
Physical mixed DPI/два монитора/floating-maximize-drag/fullscreen/blackout/человеческая
плавность/visual design нового ZIP не заявлены пройденными. Конкретный checklist:
build_support/README.md. Прежние W2/iteration7 результаты не перенесены на новый ZIP.

Git финализируется только после итоговых тестов/сборки по прямому разрешению владельца;
точные commit/PR/remote CI фиксируются отдельным handoff, без изменения проверенного
runtime. Публичного release нет. Существенных неразрешённых продуктовых вопросов нет;
остатки перечислены как согласованные границы и физические gates, без дублирования задач.
