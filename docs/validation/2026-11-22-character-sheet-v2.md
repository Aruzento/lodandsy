# Лист персонажа v2 и экипировка — инженерный отчёт

22.11.2026. ARU-65/80/83; gate ARU-84 сохранён. Задание
`C:/Users/Aruko/Downloads/LODANDSY_character_sheet_v2.md` прочитано полностью.
Выполнены A–E; финальные артефакты и результаты сборки перечислены в конце.
Ручная приёмка владельцем остаётся отдельным этапом. Commit/push/merge/release
нового пакета не разрешены и не выполнялись.

## Baseline и принятое решение

Фактический исходный HEAD/local origin ref:
`fee0106e6fc9177db3438332d83a3cd46a75d4a7`, ветка `codex/ui-acceptance-fix`.
[CI44950034132](https://github.com/Aruzento/lodandsy/actions/runs/44950034132)
completed/success проверен через gh. Исходный tracked tree был чистым; четыре
private untracked вложения/локальный аудит сохранены и исключаются из поставки.
Новый runtime не опубликован в GitHub, remote CI относится к исходному коммиту.
Итерация7/A–G и прежний A–I повторно не реализовывались.

Изучены AGENTS/START/README/MVP, ADR-027/030/031/032/033/034, последний validation
report и актуальные Linear ARU-65/80/83/84. Обнаруженные заменяемые пути подтверждены
кодом: Card armor_type/armor_base/shield, synthetic Card shield source в calculate,
template inventory без active, отдельные proficiency forms/results в game_sheet.

На границе формата был подготовлен ADR-035 и задан вопрос о SQLite15. Владелец
ответил: «все миры тестовые», явная замена и удаление legacy допустимы. Вопрос закрыт:
переход/конвертация не реализуются. **SQLite16/Card7**, Map7/Actor1/Table3/UIstate4
сохранены; Rules envelope1, профиль dnd_5e_2014 version2. SQLite15/Card6/profile1
явно отклоняются без перезаписи. Миграторов, fallback старых полей и удаления миров нет.
Промежуточный stage-b report остаётся историей до этого решения, не итоговым статусом.

## Референсы и визуальное решение

Изучены [Long Story Short — снимок листа](https://longstoryshort.app/doc/vortex/adding-characters/),
[слои бонусов](https://longstoryshort.app/doc/character-sheet/bonuses/) и
[контракт персонажа](https://longstoryshort.app/doc/developers/characters/).
Публичный снимок просмотрен локально; в repo/app/ZIP не включается. Приняты группировка
по характеристикам, компактная строка владение/название/итог, прямое поле числа и
детали показателя по нажатию. Чужой порядок бонусов, серверная модель и код не копируются.

Дополнительно изучены [D&D Beyond players](https://www.dndbeyond.com/en/players),
[sheet revamp](https://www.dndbeyond.com/posts/262-the-character-sheet-revamp-is-live-now),
[Foundry AC provenance](https://github.com/foundryvtt/dnd5e/wiki/Roll-Formulas),
[Basic Rules2014 equipment](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/equipment),
[создание персонажа](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/step-by-step-characters),
[терминология характеристик](https://5e14.dnd.su/articles/newbie/468-using-ability-scores/)
и [снаряжения](https://dnd.su/articles/inventory/147-armor-arms-equipment-tools/).
Aether Keep: www timeout, основной host HTTP403; доступный внешний вид не выдан за
изученный. Никакие справочники/портреты/изображения/закрытый код не импортировались.
SRD attribution и прежние лицензии остаются в поставке. Новых dependencies нет.

Применены native layout/типографика/доступность better-ui. Реальный Qt render
осматривался и исправлялся: начальная полоса ресурсов была слишком высокой,
editable combo обрезал текст из-за вложенного padding, readonly индикаторы были
слишком бледными, узкий context selector сжимался кнопками. Исправлены эти дефекты,
убраны повторные поля результатов, источники показаны по необходимости.

## A/B. Нативный лист и адресованный ввод

`ui/ability_block.py` заменяет прежние маленькие tiles и отдельные skills/saves forms:
шесть блоков, первая строка save, затем собственные навыки в русском алфавитном порядке.
Все18skills и6saves присутствуют ровно один раз. ○/●/◆ различают0/1/2 и имеют русские
accessible names/tooltips; saves переключаются между0/1. Native buttons доступны
клавиатурой, не используют dropdown. Итог справа читается из EffectiveValues.

Рядом с крупным модификатором постоянно виден SemanticLineEdit базового числа.
В Actor context число readonly/effective, происхождение базы — tooltip и подпись при
отличии, переход «К базе» явный. Actor не создаётся просмотром и не получает копий
характеристик. FieldEdits/ValueAddress/expected value/owner generation, Enter/Tab/
blur/Escape/Ctrl+S и explicit conflict resolve сохранены; второй edit manager не создан.

`ui/character_header.py`: native editable race/class/subclass suggestions и уровень.
Пустое значение и homebrew сохраняются. Class change меняет подсказки архетипа, но
не удаляет несовместимый сохранённый выбор: показывает уведомление. В Actor context
общие сведения readonly; header не выдаёт расовые/классовые бонусы и не является wizard.
Стабильный `subclass` добавлен в действующий FieldDefinition, без параллельной схемы.

`ui/game_sheet.py`: resource strip current/max/temp HP, один AC, initiative/speed/
proficiency; без Actor current/temp не подставляются. HP progress безопасен при max0/
unknown. HP/speed settings раскрываются по нажатию; крупный AC и его заголовок открывают
один `ui/armor_details.py`. 3/2/1 ability columns по viewport, один vertical scroll,
узкий context занимает отдельную строку. Настройки HP/XP/атаки/магия/нагрузка доступны
ниже. Для Object только применимые поля; обязательный Card hero/portrait/tabs и native
QTextDocument/section UUID/Undo сохранены. Game fields не возвращены в technical Inspector.

[Матрица79FieldDefinition/12типов](2026-11-22-character-sheet-v2-fields.md) фиксирует
принадлежность и UI. `aliases` сохраняет data-only статус, Object.player по-прежнему
не разрешён application contract. Canonical IDs не русифицируются, «Анализ» — UI label
существующего investigation. Qt translations и русская диагностика сохраняются.

## C. Item, inventory и защита всех путей

`domain/card_schema.py`: Item equipment_kind=item/armor/shield, armor_category,
armor_ac, nullable shield_bonus. None для shield_bonus означает профильные+2,
ноль сохраняется нулём. `ui/item_page.py` показывает только применимые typed controls;
rarity/weight/cost и редактор универсальных modifiers сохранены. Item не хранит equipped.
Старые Card armor_type/armor_base/shield полностью удалены из stored fields и writers.

Единственный источник участия — active cell строки Table. Template создаётся с
active=false; создание Actor копирует template с новыми row/column IDs по существующему
контракту. Item UUID остаются ссылками, дальнейшая активность индивидуальна. Чтение
inventory не создаёт Table. Статус «Надет/Снят» для armor/shield, «Активен/Неактивен»
для обычных Item выводится через generic caption hook; quantity не множит вклад.

`domain/equipment.py` содержит immutable EquipmentEntry/EquipmentFacts и pure resolver.
Integration `document_payloads.inventory_inputs` разрешает rows/Item refs и передаёт
facts и прежние ModifierSources в calculate. В Actor state нет копии доспеха/щита.
Неполный active armor и отсутствующая active Item ref дают incomplete/диагностику,
не unarmored default. Missing Item остаётся мягкой ссылкой, без удаления строки.

Один armor/один shield проверяются final validate_project при service/generic payload/
table replacement/import/load и изменении категории Item. Конфликт не разрешается
порядком строк. `ProjectActions.set_inventory_activity` с explicit replace меняет
строки одной транзакцией, guard=(generation,serial) и expected Table. UI предлагает
replace/cancel; отмена ничего не пишет. API без разрешения замены отвергает конфликт.
Scalar equipment Undo не добавлен; адресованная история размещений сохранена.

Tables получает только generic cell command/caption/dependency hooks из composition
root, не импортирует D&D rules/Equipment widgets. Для обычного template Table сохраняется
возможность структурного редактирования: испорченные inventory descriptors дают
incomplete inputs вместо ложного AC. Owned inventory сохраняет строгую схему.
Это сохраняет обычную Table и закрывает обход расчёта удалением/сменой типа active column.

## D. Pure AC и синхронизация

Profile2: unarmored10+DEX; light armor_base+DEX; medium armor_base+min(DEX,2), включая
отрицательный DEX; heavy armor_base. Один shield даёт его typed bonus (стандарт+2),
затем действуют прежние modifier stages/source identities. Автоматического второго
shield source из Card нет. Manual Card/Actor AC — конечный итог, auto показан отдельно.
Новая Card по умолчанию использует auto AC; manual выбирается явно.

armor_type/armor_base/shield и base_ имена сохраняются только как typed resolved formula
inputs. Writer ValueAddress для них отсутствует. Старый профиль1 отвергается; в новом
safe имена доступны, unknown/type/cycle/error блокируют preview/apply. Формула AC
задаёт основу/DEX, shield и Item sources добавляются после неё — это объяснено в UI.
Safe AST, budgets/DAG, отсутствие eval/exec и revision/serial/generation guards сохранены.

AC dialog показывает выбранный доспех/категорию/основу, DEX и учтённую часть, shield,
прочие modifiers и итог. Изменение экипировки — через inventory, ручного переключателя
вида брони/щита в диалоге нет. Card/Actor manual fields используют тот же FieldEdits.
Закрытие или смена Actor завершает только своих owners; stale dialog не меняет чужой ref.

EffectiveValues содержит readonly facts/sources. Addressed notifications учитывают
смену происхождения даже при равном числовом AC: переименование Item или категория
обновляют breakdown. base_effective_changed обновляет базовый лист без Actor; Actor
events обновляют личный лист, Map Inspector и все размещения shared Player. Нет broad
editor/scene reset, нового канона, ORM, EventBus или service locator.

## Критерии1–7: проверенная часть и физический gate

| Критерий | Подтверждено | Отдельная ручная проверка |
|---|---|---|
|1|18skills/6saves, ХАР13/БМ3→+1/+4/+7, save+1/+4, proficiency сохраняется|Удобство выбора владения и чтения|
|2|InlineDEX14→16, modifier/skills/initiative/AC sync; readonly Actor base, focus/Escape/conflicts|Два окна с физическим вводом|
|3|Race/class/subclass/level, homebrew/unknown; incompatible subclass сохраняется с уведомлением; reopen|Понятность header и подсказок|
|4|DEX16:13/14/16/16/18, shield+2; DEX8 medium13/heavy16; qty8/12 не множит; duplicate guards/cancel/one commit replace|Ручное надевание из нового ZIP|
|5|Manual21 сохраняется, auto актуален; independent Actor, live Item/template; missing ref incomplete, нет копий facts|Shared Player на физических Viewer/мониторах|
|6|Backup/reopen/UUID/refs/rules, malformed/import/replacement/load fail closed; schema15 hash неизменен при отказе; Map/Undo/fog suites|Свой новый мир и backup в установленном ZIP|
|7|Native wide/narrow renders, 3/2/1 без horizontal scroll, scales100/125/150/200%; компактный AC/Item UI|Physical docking/maximize/focus/mixed DPI/два монитора и clean Windows|

## Проверки

Все команды используют `.prototype-deps/locked-venv/Scripts/python.exe` (CPython3.14.8,
PySide6 6.11.2, Qt ADS5.1.1, прежние lockfiles). Полный baseline от green fee0106 не
повторялся. После блоков выполнялись targeted batches; финальный runtime прошёл:

| Команда / gate | Результат |
|---|---|
|Targeted equipment/Actor/storage/fields/inventory/architecture|72 passed на этапе интеграции|
|Targeted live provenance/новый UI/architecture|29 passed до финального gate|
|`QT_QPA_PLATFORM=windows python -m pytest -p no:cacheprovider`|510 passed, 1 skipped, 98.82s|
|`QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_map_fog.py tests/test_conflict_resolution.py tests/test_project_catalogue.py tests/test_game_sheet_ui.py tests/test_character_sheet_v2_ui.py tests/test_equipment.py -p no:cacheprovider`|76 passed, 10.32s; прежний fixture rewrite warning|
|`python -m ruff check .`, `python -m pip check`, `git diff --check`|проходят; только Git LF→CRLF notices|
|`python -m prototypes.architecture_graph --report docs/architecture/imports-character-sheet-v2.json`|105 modules/264 edges/0cycles|
|Windows PyInstaller build + `python -m build_support.verify_frozen`|107 compiled modules, no mismatch/missing/obsolete|
|Source/frozen/portable `--self-test` с NASA233MP|все три passed, typed equipment AC/manual final включены|
|ZIP CRC/MANIFEST/source/binary identity|passed; финальная квитанция рядом с ZIP|

Skip — право Windows на symlink недоступно; junction/security сценарии сохранены.
Первый full run обнаружил только устаревший список четырёх inventory columns в тесте;
обновлён до пяти, все проверки UUID/Undo/shared Table сохранены. Последующий green gate
и финальные gates после default auto AC и уточнения profile applicability выполнены.
Профиль D&D применяется только к Character/Creature/Object; Item/Note и прочие типы
сохраняют declared values без фиктивных игровых AC/skills в preview. Тесты не ослаблялись:
добавлены matrix/duplicate generic/import/type change/load/stale/manual/soft ref/
provenance/subclass/old-file hash regressions. Новые runtime helpers явно Cards-owned.

## Визуальные доказательства и ограничения

Production QWidget.grab из `prototypes/ui_acceptance_preview.py`, QPA windows, отдельные
TemporaryDirectory world/QSettings. Это настоящий рендер виджетов с рабочими bindings,
не HTML-макет. Проверены обычный workspace, wide1040/medium660/narrow400, base/Actor,
Object, Item types, inventory, AC details и оперативный Map Inspector; изображения
перечислены в финальном evidence ниже. После снимков исправлены геометрия и читаемость.

Финальные снимки повторены после последнего изменения runtime: [workspace](2026-11-22-character-sheet-v2/01-character-workspace.png),
[wide1040](2026-11-22-character-sheet-v2/02-character-wide.png),
[medium660](2026-11-22-character-sheet-v2/03-character-medium.png),
[narrow400](2026-11-22-character-sheet-v2/04-character-narrow.png),
[Card base](2026-11-22-character-sheet-v2/05-base-card.png),
[Object](2026-11-22-character-sheet-v2/06-object.png),
[AC breakdown](2026-11-22-character-sheet-v2/12-ac-details.png),
[armor Item](2026-11-22-character-sheet-v2/13-equipment-item.png),
[shield Item](2026-11-22-character-sheet-v2/14-equipment-item.png),
[active inventory](2026-11-22-character-sheet-v2/15-equipped-inventory.png).
Остальные кадры07–11 подтверждают modifier dialog/rules/Map Inspector.
В том же каталоге — `dpr-1.25/1.5/2-{wide,narrow,ac}.png` и evidence JSON с фактическим
device_pixel_ratio. Осмотрены итоговые wide/narrow, Item, inventory и AC; переполнения
самого листа нет. Обычная Table сохраняет свою горизонтальную прокрутку. При200%
доступная высота экрана ограничивает окно; нижние блоки доступны vertical scroll.

Computer-use и Browser-use не смогли инициализироваться: `failed to write kernel assets:
Системе не удается найти указанный путь. (os error 3)`. Поэтому desktop/compositor capture
и физические мышь/мониторы не заявляются. QT_SCALE_FACTOR не равен physical mixed DPI.
В предыдущем narrow render при высоком DPR native hero title может прокручиваться
внутри QLineEdit; горизонтального scroll листа нет, обязательный hero layout не заменён.

## Поставка и состояние

Сборка выполнена `powershell -NoProfile -File build_support/build_windows.ps1 -Python
.prototype-deps/locked-venv/Scripts/python.exe -SkipPackage`, после финальной правки
profile scope — повторным `python -m PyInstaller --noconfirm --distpath
.prototype-deps/mvp-dist --workpath .prototype-deps/mvp-build build_support/windows.spec`.
Последний verify_frozen сравнил107 скомпилированных модулей с checkout, без расхождений.
Runtime после этого не изменялся. Доказательства:
[parity](2026-11-22-character-sheet-v2/frozen-source.json),
[source smoke](2026-11-22-character-sheet-v2/source-smoke.json),
[frozen smoke](2026-11-22-character-sheet-v2/frozen-smoke.json),
[portable smoke](2026-11-22-character-sheet-v2/portable-smoke.json).

Source: `python -m build_support.windows_smoke --self-test --report <report>
--large-map-image .prototype-deps/nasa-blue-marble.jpg`. EXE: те же аргументы
`--self-test --report <report> --large-map-image <absolute image>`. Изображение21600×10800,
233.28MP, приватный cache; в ZIP не входит. Все три smoke проверили save/reopen/backup,
UUID/инвентарь/Actor/rules, manual final, typed armor+shield, map/fog/layout/Tools.

Portable запущен из свежего распакованного ZIP в каталоге
`.prototype-deps/Проверка ZIP лист персонажа v2 2026-11-22/LODANDSY`, cwd=Windows TEMP,
PATH только Windows/System32+Windows; PYTHONHOME/PYTHONPATH/QT_PLUGIN_PATH/QML2_IMPORT_PATH
очищены. Exit0, frozen=true, passed=true. На хосте установлен Python: это проверка
самодостаточности bundle, а не доказательство clean Windows. После включения JSON и
финального отчёта ZIP перепакован; все130 EXE/DLL/PYD побайтно сравниваются с уже
проверенной свежей распаковкой. Повторный runtime smoke для изменений только отчёта
не требуется. Все source MANIFEST entries проверяются и по SHA, и по текущим байтам repo.

Новый кандидат: `.prototype-deps/LODANDSY-Character-Sheet-v2-2026-11-22.zip` и внешний
`.zip.sha256`. Source manifest, CRC, binary identity, exact bytes/SHA — во внешней
квитанции `.prototype-deps/character-sheet-v2/delivery-final.json`; checksum вне ZIP
устраняет циклическую зависимость собственного отчёта. Предыдущий ZIP остаётся прежней
версией, не выдаётся за новую. Exact source/docs/tests/licenses входят в новый bundle;
private references, реальные миры, кеш и внешний референс LSS исключены.

ARU-65/80/83 обновлены кратким статусом в существующих записях и остаются In Progress до ручной приёмки.
Автоматическая проверка отклонила подробное внешнее обновление с локальными путями,
хешами и сведениями о неопубликованной сборке. Разрешённое краткое обновление без этих
данных выполнено; подробности находятся в этом локальном отчёте и квитанции поставки.
ARU-84 Done не переоткрывался; ARU-64/clean Windows отдельно. Существенных нерешённых
продуктовых вопросов после разрешения удалить legacy нет. Git HEAD fee0106, изменения
локальные; новых commit/push/merge/release нет. Полный snapshot/synchronous backup
и известные bounds сохранены; новый combat/effects/slots/class wizard не добавлен.
