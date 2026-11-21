# Исправление UI-приёмки Cards / Actors / 5e14 — 21.11.2026

Задание: `LODANDSY_UI_acceptance_fix.zip`, прочитаны 00_START_HERE, 01_REQUIREMENTS,
02_ACCEPTANCE, 03_CODEX_PROMPT; проверены SHA256SUMS. Выполнены блоки A–F. Это исправление
непройденной ручной приёмки, не повторная реализация прежнего A–I и не приёмка человеком.
Владелец прямо отменил Inspector-only ввод игровых полей. Действующие игровые решения
ADR-033, границы ADR-027 и lifecycle/drafts ADR-032 сохранены. Новых продуктовых решений
и неподтверждённых механик нет. Commit/push/merge/release этим запросом запрещены.

## A. Фактический baseline, источники и расхождения

До правок main/local HEAD/origin/main и GitHub main совпали:
`8f73f060439d5a24875c546df4da77277d7bf580`. GitHub CI44912417146 success:
478 native cases (477 passed/1 skip), 44 offscreen. Это проверка исходного main,
а не CI текущих незакоммиченных изменений. Первоначальное tracked tree было чистым.
Существующие untracked private attachments, references и локальный архитектурный
черновик не удалены, не изменены и не включаются в ZIP. Личные миры не открывались.
Все GUI проверки используют новые disposable worlds и отдельный QSettings catalogue.

Изучены AGENTS.md, START-CODEX.md, README.md, docs/MVP.md, ADR-027/030/031/032/033,
validation/2026-11-20-iteration-7{,-stabilization}.md, предыдущий отчёт Cards/Actors,
architecture/LODANDSY.drawio и актуальные ARU-65/80/83/84. В ARU-65/80/83 прочитаны
замечания владельца о непройденном UI. Стабилизация итерации7 завершена; A–G не повторялся.
Исторические HEAD751b699/9e06c0b и SQLite14/Card5/Map6 больше не актуальный baseline.

Старая документация и прежний пакет разрешали ввод игровых полей/модификаторов и вход
в правила из Inspector. Новый архив явно меняет этот UI контракт: системные вкладки
карточки и gear справа. Расхождение зафиксировано ADR-034; README/MVP/START/AGENTS и
дополнения ADR-027/032/033 приведены к новому решению. Card→Actor→Token и форматы сохранены:
SQLite15/Card6/Map7/Actor1/Rules1/Table3/UIstate4. Domain, SQLite store/codecs не менялись.

Терминология сверена по [характеристикам D&D](https://dnd.su/articles/newbie/468-using-ability-scores/)
и [русскому листу](https://dnd.su/storage/files/DnD5e_character_sheet_RUS.pdf).
Лист и тексты правил не копировались. Применены native layout/типографика/доступность
из better-ui; никаких новых зависимостей, HTML канона или web runtime.

## B. Системные страницы и адресация

`ui/card_editor.py` добавляет виртуальные страницы `system:attributes` для
Character/Creature/Object и `system:modifiers` для Item. Они не Card Section и не
RichDocument, не получают фиктивный UUID и не записывают игровые значения в content.
Обычные вкладки сохраняют UUID, порядок, rename/delete, позиции, QTextDocument и Undo.
`ui/card_document_state.py` разрешает только два известных UI keys в active_section;
прежние UUID и некорректные настройки обрабатываются безопасно. Формат UIstate4 сохранён.

`application/game_sheet_binding.py` принадлежит Cards. По умолчанию показывает базу,
просмотр не создаёт Actor. Контекст участника выбирается явно, включая переход из
«Связей» и токена карты. База read-only в Actor context; запись идёт только по его
ValueAddress через существующие FieldEdits, expected value и owner generation.
Переключение завершает только свой ввод. Конфликтный/невалидный draft остаётся на
прежнем адресе. Другое представление/Inspector не переназначается на выбранного Actor.

Инвентарь участника открывается по owned Table UUID. Обычная вкладка inventory явно
подписана как базовый шаблон новых участников; глобальный Item не получает equipped.
Maps получает callback перехода в лист через composition root, без доступа к private
виджетам Cards. Единственный канон и transactional/post-commit pipeline сохранены.

## C. Лист, Inspector и русский интерфейс

`ui/game_sheet.py`: вверху HP/КД/скорость, current/temp для Actor, auto/manual для базы,
раскрываемый личный final override. Нулевой/неизвестный максимум безопасен, процент
производный. Затем инициатива/уровень/мастерство/пассивное Восприятие, шесть плиток
modifier (effective score), подпись базы и явное редактирование базового числа.
Плитки 6/3/2 колонки зависят от фактического scroll viewport, ресурсы 3/2/1.
Один вертикальный scroll; поля не растягиваются по высоте. Спасброски, 18 навыков,
защита, уровень/опыт, прогрессия хитов, атаки, заклинания и источники раскрываются.
Object не получает класс, игрока, навыки или заклинания; применимые дополнительные
abilities доступны отдельно. Missing/unsupported и происхождение показаны явно.

`ui/hit_history.py` заменяет видимый CSV редактированием прироста по уровням: целые
значения, подписи, сохранение/отмена. Старый parse/validation остаётся каноническим.
`ui/game_labels.py` переводит labels, choices, статусы, ошибки и единицы на границе UI;
itemData/ключи не переводятся. Пользовательские имена предметов не изменяются переводом
источников. Qt standard buttons/dialogs используют штатный `qtbase_ru.qm`; ресурс
явно включён в Windows spec. Языковые ID не записываются в мир.

`ui/inspector_panel.py`, `application/card_inspector_binding.py`: Card Inspector
технический, без дублирующих игровых полей; location и прочие доступные свойства
сохранены. Actor/Map Inspector сохраняет оперативные current/temp, личные overrides,
выбор/адресное обновление, read-only calculations и переход к личному inventory/листу.
Порядок отдаёт приоритет HP/КД, высота tabs — по содержимому, нет большого пустого блока.
Участник имеет компактное current/max/КД резюме. CardsService participant DTO получил
только русские подписи tooltip. Геометрия/жизненный цикл редактора rich text сохранены.

[Матрица всех 77 FieldDefinition и 12 типов](2026-11-21-ui-fields.md) показывает scope,
UI владельца и доступность. Единственное data-only поле aliases уже до этого пакета
было resolver metadata; новый конструктор переменных не вводился. Object.player —
известный schema superset, уже запрещённый CardsService; UI не предлагает это действие.

## D. Предметные модификаторы

`ui/item_page.py` и `ui/modifier_editor.py`: rarity/weight/cost, компактный список,
Add/Edit/Remove и явные Apply/Cancel. Native ModifierDialog содержит поиск и закрытый
select только DEFAULT_FORMULAS targets, русские операции/совмещение, числовой operand.
UUID существующего модификатора сохраняется; новый выделяется один раз. Group/priority/
condition раскрываются отдельно. Неподдерживаемые condition/target явно диагностируются,
не исчезают при загрузке; произвольная цель не вводится. Удаление подтверждается при
применении. Нет широких колонок и UI JSON; JSON остаётся только внутренним транспортом
старого FieldEdits parse. Cancel формы не меняет канон, конфликт имеет UseSaved/ApplyMine.
Конфликтный список показывается человеческим текстом, не serialization dump.

## E. Правила из шестерёнки

`application/app_controller.py`/`project_controller.py`: пункт «Игровая система и
правила…» в существующем правом gear. Без проекта disabled, без выбранной Card доступен.
Одно окно текущего проекта; при смене мира закрывается, поздний callback не применяет
старое preview. Закрытие неприменённого draft запрашивает подтверждение внутри продукта.
Inspector button удалён; root внедряет только публичные callbacks.

`ui/rules_editor.py`: native категории/русский поиск, описание стандартной/изменённой
формулы, advanced безопасный синтаксис и вставка известных токенов. Типизированные
подписанные example inputs определяются зависимостями; hp_gains редактируется по уровням.
Пример ТЕЛ16→3 работает без JSON. Preview — scrollable table с before/after участников,
базы и отдельными HP clamp, без ограничения 20 строк. Кнопки в двух фиксированных рядах,
пример рядом со своими inputs. Ошибки, цикл/self-dependency/unknown input/stale блокируют
apply. Reset — только draft, затем preview/apply. Редактирование не меняет мир;
revision+serial+generation guards и safe AST/domain algorithms не изменены.

## F. Проверки, артефакты и пределы доказательства

Рабочий Python `.prototype-deps/locked-venv/Scripts/python.exe`: CPython3.14.8 x64,
PySide6 6.11.2, Qt ADS5.1.1, исходные lockfiles. В командах ниже `python` означает его.

| Проверка | Фактический результат |
|---|---|
| Targeted существующего UI/Actor/semantic/section/type coverage | 44 passed на этапе переноса |
| Новый UI + architecture targeted | 24 passed, 5.17s |
| `QT_QPA_PLATFORM=windows python -m pytest -p no:cacheprovider` | 489 passed, 1 skipped, 99.24s |
| `QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_map_fog.py tests/test_conflict_resolution.py tests/test_project_catalogue.py tests/test_game_sheet_ui.py -p no:cacheprovider` | 56 passed, 7.27s; прежний fixture import warning |
| `python -m ruff check .` / `python -m pip check` / `git diff --check` | проходят; Git предупреждает только о будущей нормализации LF→CRLF двух файлов |
| `python -m prototypes.architecture_graph --report docs/architecture/imports-ui-acceptance.json` | 101 modules / 250 edges / 0 cycles |
| Source `--self-test --large-map-image .prototype-deps/nasa-blue-marble.jpg` | passed, QPA windows, isolated world |
| `powershell -NoProfile -File build_support/build_windows.ps1 -Python .prototype-deps/locked-venv/Scripts/python.exe -SkipPackage` | exit0; PyInstaller build complete |
| `python -m build_support.verify_frozen --report .prototype-deps/ui-acceptance-frozen-source.json` | 103 compiled modules, 0 mismatch/missing/obsolete |
| Frozen EXE `--self-test --report … --large-map-image …` | passed, exit0, frozen=true/windows |
| Extracted portable EXE, Unicode directory, cwd TEMP, Windows-only PATH, PYTHONHOME/PYTHONPATH/QT_PLUGIN_PATH/QML2_IMPORT_PATH cleared | passed, exit0, frozen=true/windows |
| ZIP CRC, source MANIFEST, private exclusions, Qt translation, binary identity | passed; 130 EXE/DLL/PYD identical to the extracted smoked candidate |

Skip — Windows account не разрешает создание symlink; junction/security тесты остаются.
Первый full run обнаружил тест, привязанный к нулевой строке layout inventory: после
добавления подписи он находил QLabel. Исправлен поиск Table по прежнему UUID, проверки
live projection/адресных событий/отсутствия rebuild сохранены. Полный gate повторён
успешно. Новый smoke также приведён к lifecycle native QPushButton и дополнительному
временному Item window; это правки harness, не ослабление предметных инвариантов.
После этих harness-only изменений runtime/full suite не менялся.

Новые meaningful UI сценарии: виртуальная вкладка без DB Section/Actor, reopening,
8/10/12/16 modifiers, полная доступность полей, Actor A/B/draft/conflict адресация,
44→49 без лечения и 49→44 clamp через active Item, нулевой max, adaptive native widths,
typed modifier/cancel/UUID/conflict, native история accept/cancel, malformed UI settings,
gear/typed example/1÷0/stale/несохранённое закрытие. Старые domain/save/Map/inventory/
backup/references/Undo/security проверки не ослаблялись. Явная ownership allowlist
дополнена ровно пятью Cards helpers; новых cross-feature исключений нет.

## Визуальная итерация

Проверялись production QWidget.grab PNG из `prototypes/ui_acceptance_preview.py`, QPA
windows, синтетический временный мир. После просмотра исправлены начальный reflow
после layout, лишняя высота технического Inspector/Item list, видимость Actor overrides
без Actor, контраст ресурсных рамок, положение Test/preview и compact Map Inspector.
Это просмотр реального Qt рендера, не макет из HTML и не физическая приёмка.

Computer-use не смог инициализировать kernel assets: `failed to write kernel assets:
Системе не удается найти указанный путь. (os error 3)`. Повторная инициализация и CUA
дали ту же ошибку. Поэтому desktop/compositor capture, движения мышью, физические
мониторы и DPI не подтверждаются этими снимками. Снимки не содержат приватных портретов.
Финальные снимки: [обычная рабочая среда](2026-11-21-ui-acceptance/01-character-workspace.png),
[узкая карточка](2026-11-21-ui-acceptance/04-character-narrow.png),
[база](2026-11-21-ui-acceptance/05-base-card.png), [объект](2026-11-21-ui-acceptance/06-object.png),
[предмет](2026-11-21-ui-acceptance/07-item-list.png), [форма](2026-11-21-ui-acceptance/08-item-form.png),
[пример правил](2026-11-21-ui-acceptance/09-rules-example.png),
[малое окно640×480](2026-11-21-ui-acceptance/09b-rules-small.png),
[preview/clamp](2026-11-21-ui-acceptance/10-rules-preview.png),
[карта/Inspector](2026-11-21-ui-acceptance/11-map-inspector.png).

Дополнительно выполнен production Qt render с QT_SCALE_FACTOR=1.25/1.5/2,
метаданные фактического DPR1.25/1.5/2 и снимки малого окна правил включены:
[125%](2026-11-21-ui-acceptance/rules-small-dpr1.25.png),
[150%](2026-11-21-ui-acceptance/rules-small-dpr1.5.png),
[200%](2026-11-21-ui-acceptance/rules-small-dpr2.png).
При уменьшении доступной логической высоты лист использует вертикальный scroll;
эти запуск/рендер-проверки не означают испытания смены physical mixed DPI монитора.

## Матрица повторной приёмки U01–U18

| ID | Автоматически/визуально подтверждено | Что остаётся человеку |
|---|---|---|
| U01 | Virtual page ровно одна, прежние Section/UUID и active key после reopen | Проверка своего schema15 тестового мира |
| U02 | База без Actor/current/temp, Object applicability, просмотр не создаёт Actor | Оценка понятности контекста |
| U03 | Actor A/B, FieldEdits addressing, Player/shared placements сохранены | Два Viewer на реальных мониторах |
| U04 | Modifier sign/score, обычная/узкая компоновка и edit base | Визуальная приёмка владельца |
| U05 | ТЕЛ14/5d10 history→44, +2 Item→49 без heal, deactivate49→44 clamp | Сквозной ручной ввод в новом ZIP |
| U06 | Auto/manual/final override и missing/unsupported: прежний домен + новый binding | Читаемость источников/ошибок |
| U07 | Матрица77/12, русские labels/itemData/Qt buttons, typed inputs | Русские шрифты/системный scale |
| U08 | Native text/таблицы/ссылки/sections/Undo tests, compact Inspector | Ощущение редактирования/плотность |
| U09 | Native widths1040/660/400, 6/3/2, горизонтальный scrollbar=0 | Dock/maximize/restore/drag и physical DPI |
| U10 | Закрытый target search, операции/itemData, typed form/cancel | Оценка удобства списка/формы |
| U11 | Stable UUID, Item conflict/cancel, source dedup и qty/inventory tests | Практическая правка активного предмета |
| U12 | Gear enabled без Card, single current-project window, close guard | Переключение мира в установленном ZIP |
| U13 | Русский поиск, ТЕЛ16→3, локальный draft, пример без JSON | Малый экран и physical DPI |
| U14 | Preview rows/clamp, 1÷0/stale; DAG/unknown/self-dependency domain tests | Ручной reset/cancel/preview flow |
| U15 | Semantic keyboard/focus/escape/Ctrl+S/owner-conflict suites | Два окна с физическим вводом |
| U16 | Persistence/inventory/Actor/rules/backup/schema rejection suites | Свой новый disposable мир и backup |
| U17 | Старые Map/fog/presentation/placement history gates, 233MP smoke | Плавность, blackout, сценические действия |
| U18 | Frozen/portable проверки отдельно ниже, без эквивалентности clean Windows | Вся физическая приёмка, ARU-64 |

## Linear и Git

ARU-65/80/83: существующие задачи, оставить In Progress до ручной приёмки U01–U18.
ARU-84 Done не переоткрывается: архитектурный gate сохранён. ARU-64 отдельно — чистая
Windows без Python. Дубликатов задач нет. Git HEAD/main не изменён; новые исходники,
тесты, ADR/docs/evidence остаются незакоммиченными. Никаких commit/push/merge/release.
Непроверенные физические сценарии перечислены в build_support/README.md и матрице выше.


## Windows-кандидат и воспроизводимость

Новый файл `.prototype-deps/LODANDSY-UI-Acceptance-Fix-2026-11-21.zip`, отдельный от
Cards-Actors ZIP. SHA256 находится в одноимённом `.zip.sha256` и внешней квитанции
`.prototype-deps/ui-acceptance-delivery-final.json`: checksum намеренно вне собственного
ZIP, чтобы отчёт не создавал циклическую зависимость checksum. EXE SHA256:
`cad094834c38781db5930683e1fe702fc1c452b86682d5a22b2a4ffba5e25d8a`.

Полный ZIP содержит EXE/runtime, LGPL/Qt/ADS/Python/libvips/SRD notices, исходники,
тесты, lockfiles, ADR/docs/draw.io и синтетические PNG. Source manifest проверяется
против checkout побайтно. Private references, локальный архитектурный черновик,
пользовательские миры, attachments, cache и исходная большая карта исключены.
Добавление PNG разрешено packager только для явно выделенной папки этого UI evidence.

Команды финализации:

```powershell
python -m build_support.package_windows --archive LODANDSY-UI-Acceptance-Fix-2026-11-21.zip
python .prototype-deps/verify_ui_acceptance_delivery.py --extract
# Запустить EXE в .prototype-deps/Проверка UI ZIP 2026-11-21/LODANDSY
# --self-test --report <absolute portable report> --large-map-image <absolute NASA image>
# cwd=$env:TEMP; PATH=$env:WINDIR/System32;$env:WINDIR; без Python/Qt path overrides.
python .prototype-deps/verify_ui_acceptance_delivery.py
```

Source/frozen/portable прошли один и тот же расширенный smoke: Card/Map/Editor/Table/
Dice, русский Qt, typed target search, ТЕЛ16→3, виртуальные страницы/Actor context,
shared Player/NPC copy, active Item, rules apply, semantic keyboard, refs/projections,
rich text/portrait, vector fog/player shared tiles, placement Undo, full snapshot,
backup/restore и layout/reopen. Все пути — disposable; NASA image21600×10800=233.28MP.

Доказательства внутри source docs:
[source](2026-11-21-ui-acceptance/source-smoke.json),
[frozen](2026-11-21-ui-acceptance/frozen-smoke.json),
[portable](2026-11-21-ui-acceptance/portable-smoke.json),
[compiled parity](2026-11-21-ui-acceptance/frozen-source.json).
Native/offscreen/source/build/package логи находятся в `.prototype-deps/ui-acceptance-*`.

После portable smoke добавлены только отчёт/его JSON evidence и локальная квитанция;
ZIP перепакован с актуальными документами. Итоговая проверка снова сверяет CRC/source
manifest/checksum и все130бинарников с именно распакованной проверенной копией; runtime
не пересобирался и не менялся. Последующий portable запуск не требуется для изменения
только документации. Внешняя квитанция содержит точный final ZIP SHA/bytes/file count.

Это Windows-хост с установленным Python. Очистка PATH/env и frozen запуск не равны
чистой Windows без Python; физические focus/docking/maximize/drag/два монитора/mixed DPI,
человеческая плавность и ручная оценка нового дизайна остаются за владельцем/ARU-64.
Существенных инженерных блокеров нет. Новых боевых/эффектных/пользовательских языков нет.
