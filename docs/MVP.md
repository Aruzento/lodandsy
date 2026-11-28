# LODANDSY — действующий MVP: итерация7 + Cards/Actors/5e14

Утверждённый [пакет A–G](iterations/2026-11-20-iteration-7/CODEX-ITERATION-7.md)
и прямое дополнение владельца о Card Editor определяют текущую приёмку.
Предыдущие решения, противоречащие пакету7, отменены. Архитектура — ADR-027,
проекты — ADR-040, шапка — ADR-030, presentation/fog — ADR-031, conflict drafts — ADR-032.

## Назначение и границы

Нативная локальная Windows среда ведущего: несколько Card Editors, Map Viewer,
Map Editor, Table и Dice одновременно. Qt Widgets/Python3.14/PySide6/Qt ADS,
модульный монолит без сервера/облака/web runtime. Ручной туман и отдельный player
экран приняты в итерации7. За пределами: multiplayer, streaming server, LOS,
освещение, полная автоматизация боя/эффектов, per-player visibility и внешний plugin SDK.

Единственный документ Card — визуальный ADR-014, единственная внутренняя
URI — lodandsy://entity/UUID. MOW importer полностью отменён. Для миров,
созданных в v0.01 и последующих поддерживаемых версиях, действует обязательная
совместимость по [ADR-040](adr/040-managed-projects-v001.md). v0.01 — первая
поддерживаемая база пользовательских данных. [Ручная приёмка v0.01](validation/v001-owner-acceptance.md)

## Проекты, навигация, окна

Welcome и «Открыть проект» перечисляют миры непосредственно в системном
`Документы/LODANDSY/project/`. Папка определяется через Qt. Подтверждение имени
сразу создаёт каталог и SQLite. Пользователь вводит название, видит путь и не выбирает каталог для
создания или восстановления. Каталог учитывает ограничения Windows, коллизии
имён и одновременное создание. История QSettings хранит последнее открытие и
выделяет недавний мир без автоматического открытия. Неисправные и несовместимые
миры получают диагностику. Явное «Открыть другую папку» и CLI path дают доступ
к внешним мирам. Они остаются на месте. Неудачное переключение оставляет текущий
мир и черновики открытыми.

Обозначение приложения v0.01 отделено от версий канона: SQLite17, Card8, Map9–10,
Actor1, Rules1 (5e 2014 profile2), Table4, Economy1. UI state4 хранится отдельно.
Последующие изменения формата требуют определения входной версии, проверенного
backup до записи, последовательной миграции с сохранением UUID, связей, данных и
вложений, проверки целостности и повторного открытия. При ошибке нужен откат
или неизменный исходный мир. Для изменения БД вместе с файлами нужна безопасная
конверсия копии или проверяемое восстановление обеих частей. Будущие неизвестные
версии и неподдерживаемые дорелизные прототипы отклоняются без записи и удаления.
Удаление или пересоздание исходного мира вместо миграции запрещено.

Tree содержит Card/Map/Table в общей иерархии; ID стабилен, parent существует либо
пуст, циклы/дубли запрещены, порядок непрерывен. Создание — «+» с меню, дочерние —
контекстное меню, поиск под кнопкой/Ctrl+F. Links не смешиваются с parent. Выбор Tree,
открытый документ, активное окно и UI state разделены. Tree/Inspector и rails фиксированы.
ADS размещает документы, WindowManager управляет жизненным циклом. Одна Card на ID;
повторное открытие фокусирует её, исходная Card при переходе по ссылке остаётся открыта.
«Создать папку» сразу добавляет дочернюю Card `folder` под выбранным элементом
или в корне. Имя «Новая папка» получает свободный числовой суффикс в пределах
родителя. Tree выделяет папку и открывает редактор имени. Escape оставляет стандартное имя.

Backup/restore находятся в gear правого rail у Inspector; верхнее меню не дублирует
эти команды. New/Open/Save/hotkeys сохранены. Busy/saving исключают конфликтующие
операции; backup/restore без мира недоступны. Все переключения проходят ProjectController guards.

## Card Editor и документы

Тип выбирается при создании и затем неизменяем в сервисе, collection и generic payload
mutation. Поддерживаются текущие note/article/character/location/item/object/folder
и их typed fields; прежних templates/tags нет. Характеристики редактируются в системной
вкладке карточки, технические свойства — в Inspector (переопределение ADR-034).

Обязательная нативная Qt компоновка: крупный квадратный portrait слева132–220 logical px,
справа read-only type badge, одно крупное title, inline summary. Отдельная строка
UUID tabs ниже; под ней текущий content с общим inset16px, без пустой левой колонки.
Breadcrumb, третий title, summary popup и centered760px prose удалены. Copy link —
Tree/контекст. Header не имеет отдельной прокрутки; высота согласована с шириной
портрета и не меняется от длины текста, вкладки или загрузки изображения. В узком
окне длинное summary прокручивается внутри своего inline поля, не всей шапки.

Портрет/crop хранит ссылку на исходный asset и нормализованный crop; no-op crop
roundtrip идемпотентен. Загрузка изображений не меняет геометрию. CardSection UUID
rich_text/table_ref сохраняют отдельные QTextDocument/cursor/scroll/Undo между tabs
и возвратом к документу. Rich input coalescing250ms/max2s, structured input semantic
Enter/Tab/blur/Escape/Ctrl+S. Нет canon publish на каждую букву.

Rich HTML контролируется sanitation/codec ADR-014: только текущие разрешённые
элементы, source не Markdown. lodandsy://entity/UUID разрешается application navigation
в текущем проекте; malformed/missing/unknown target безопасно диагностируется.
Переименование не переписывает пользовательский текст ссылок. HTTP/HTTPS только
при явной активации в системном браузере; сетевые ресурсы preview не загружаются.
Локальные изображения только из assets текущего проекта, traversal/symlink escape
блокируются; file/javascript/прочие URI запрещены. Вставка HTML проходит sanitizer.
В любом rich text-разделе `[[` открывает поиск по документам проекта с иконками и путями.
После выбора отображается ссылка с названием и UUID. Ctrl+щелчок переходит к цели.
Контекстное меню меняет или удаляет ссылку. Форматы заголовков применяются к абзацам,
включая выделенный диапазон, и отменяются одним действием Undo.

На листе участника каждая группа характеристик сворачивается. Название, основное
значение и модификатор остаются видимы, поля и действующие черновики сохраняются.
Характеристики изначально компактны. Подробности получают естественную высоту
из нативной раскладки при раскрытии.

Единая панель rich text даёт прямой доступ к истории, стилям, шрифту, абзацам
и вставке. Группы переносятся при сужении окна. Поддерживаемое форматирование
внешнего HTML сохраняется при вставке. «Очистить форматирование» работает над
выделением, сохраняя текст, ссылки и изображения.

## Tables, inventory, Dice

Table — UUID columns/rows и типы text/number/bool/entity_ref/projection. Перестановка
сохраняет IDs и native editor; writable TSV применяется атомарно, projection read-only.
Инвентарь — обычная дочерняя Table: item UUID, положительное целое quantity,
живые description/cost projections; стоимость0 отличается от пустого значения.
Производные cells не хранятся. Entity picker ищет title/aliases/path/UUID, не создаёт
копии Card. Удалённый item сохраняет reference/count и показывает недоступность.

FieldEdits/TablesService сохраняют invalid draft отдельно от канона. Conflict хранит
raw/base/observed независимо от native editor. Reopen/blur/unchanged commit/flush/Ctrl+S
не применяют конфликт молча. «Использовать сохранённое» не пишет в канон;
«Применить мой вариант» повторно проверяет canonical value, третья правка требует
нового разрешения. Действия доступны в Card/Inspector и embedded/standalone Tables.
Cancel/Escape старого редактора не очищает и не восстанавливает черновик другого
редактора, опубликованный позже, в том числе после semantic flush(finish=False).
Отмена собственных изменений возвращает согласованные raw/base/observed/error;
пустой canonical baseline None сохраняется. Форматы SQLite/payload не меняются.
Escape возвращает исходный draft, явный discard удаляет его. Другие валидные изменения
продолжают сохраняться. Нет широкого reset/потери Undo/caret ради уведомления.

Dice — singleton tool:dice, без мира/Entity:7типов кубиков, counts/modifier,
каждый результат/итог, copy и история50. Dice entity/random table mode отменены.
Заметки размещаются через вертикальную панель игровой карты. Маркер указывает
на существующую или явно создаваемую Card `note`, либо на выбранный инвентарь.
Двойной щелчок открывает штатное плавающее окно Card/Table. Маркер доступен ведущему.

## Карта, презентация, туман

Viewer и Editor независимы, используют один MapDocument/MapsService/Undo. Editor:
tool rail/canvas/layers/Object Card library/properties. Новый MapDocument атомарно
имеет видимый «Слой1», выбранный при первом открытии. layers_initialized в payload
позволяет один раз инициализировать поддерживаемую пустую карту; удаление последнего
слоя не воскрешает его. Явное добавление слоя доступно всегда. Front layer сверху.

Object Card library принимает только object с main image; import создаёт Card.
Размещение сохраняет original aspect/alpha, long-edge128 без portrait crop. MapGrid
по умолчанию opacity0.25; explicit user settings сохраняются, world coordinates не
зависят от zoom/DPI, snap отменён. TokenInstance обязательно ссылается на Card;
ПКМ «Открыть карточку»/«Копировать токен»/«Удалить токен». Удаление токена не удаляет Card или
другие размещения. Подтверждённое удаление Card атомарно удаляет её TokenInstances;
неожиданные broken references диагностируются. Доменные footprint/overrides сохранены.

У токена карточки «Объект» в Viewer есть угловые ручки дробного масштабирования
и ручка вращения. Shift при вращении даёт шаг 15°, Alt/Shift при масштабировании
управляют пропорциями и центром. Escape отменяет жест, завершение даёт один шаг
Undo. Презентация использует итоговую повёрнутую геометрию под туманом.
Map10 сохраняется с проверенной копией существующего мира перед переходом.
[Контракт трансформации](adr/036-map-interactive-tools.md)

Поиск добавления токенов использует общий EntityPicker с фильтрами типов,
иконками и путями карточек. Контекстное меню размещения даёт команды скрытия и
показа. Для Actor предусмотрены команды визуальной отметки смерти и оживления.
Скрытый токен остаётся управляемым в Viewer. Проекция Player исключает его до
загрузки графики. Маркеры заметок и состояния размещений сохраняются в Map11.
При размещении заметки ведущий выбирает «Записка» или «Инвентарь» и вводит название.
Новый документ появляется непосредственно под картой в Tree. Двойной щелчок по
маркеру открывает этот документ в плавающем окне, а удаление маркера сохраняет
документ. Инвентарь карты использует общую таблицу с ценой и весом предметов,
собственным кошельком и вставкой лута.
[Контракт Map11](adr/041-map11-token-states-and-notes.md)

Монитор на Viewer toolbar открывает одно отдельное native presentation окно на map ID.
Первое открытие сохраняет фокус GM, повторное активирует существующее окно. F11 или
double-click canvas переключает fullscreen, Escape выходит. Только карта/рамка ОС,
без toolbar/Inspector/status/scrollbars/context/drop/selection/GM tooltip. Окно не
входит в ADS/layout и не открывается автоматически после reopen. Camera следует
Viewer; другое aspect даёт чёрный letterbox вместо дополнительной видимой территории.

Viewer/Editor/Player читают один immutable map/fog snapshot и shared bounded tiles/media.
Сцены role-specific из общего MapView renderer. До актуальных map+fog+camera — чёрный
экран. Удаление/закрытие Viewer, смена/закрытие мира, shutdown закрывают player и связи;
закрытие player сохраняет остальные окна. Удаление монитора возвращает окно на доступный.
Transient object/token drag по ID не пишет SQLite и не создаёт ревизии на каждое движение;
один завершённый жест делает один commit, отмена возвращает transient в исходную позицию.

Inspector показывает параметры активного инструмента игрового Viewer. В режиме
выбора он показывает свойства фигуры, участника или действие свойств портала.
У выбранного токена в Inspector доступен существующий режим измерения расстояния.
Верхняя панель действий и «Сетка и масштаб» сохранены.

Fog toolbar открывает/скрывает только контекстные инструменты. Кисть скрывает мазок
с регулируемым world size; ластик вычитает из всех затронутых regions. Polygon:
клики/последний сегмент/замыкание по первой точке или Enter, Escape отменяет;
>=3 различных точки, без самопересечений/degenerate shapes. Выбор topmost region
по видимому фрагменту, Delete удаляет только его; остальные перекрытия сохраняются.
Один stroke/erase/polygon/delete — одна Map Undo команда. Space — pan, токены не двигаются.

FogRegion(UUID,rings)/FogState — числовые world coordinates, odd-even region geometry;
holes/split components сохраняют ID, пустые regions удаляются. Qt adapter делает
union/subtract только при командах; renderer использует нормализованный winding
без повторных costly unions. Лимиты256regions/8192points-per-region/65536total,
512samples/gesture,8MiB serialized fog; превышение отменяет всю команду с сообщением.
Никакого bitmap всей карты или отдельного player хранилища. Области вне фона, где
размещены объекты, тоже входят в world bounds и могут быть закрыты.

GM видит default50% alpha, player —100% black foreground поверх tiles/grid/objects/
tokens с консервативным непрозрачным краем. Один canonical geometry snapshot,
разные visual роли. Unfinished erase/polygon не раскрывают player ни на кадр;
движение токена не открывает туман автоматически. Начальная карта без fog.

Libvips tiles: source≤2GiB, derived cache≤4GiB/32768tiles, worker≤512MiB/900s,
shared tileLRU64MiB; rebuild/cancel/checksum/version/atomic publish сохраняются.

## Хранение, проверка и поставка

Один канон EntityCollection и SQLite17/Card8/Map9–10/Actor1/Rules1(profile2)/Table4/Economy1 через sqlite3, assets отдельно
с относительными путями; UI state4 отдельно. FK на каждом connection, составные
операции транзакционны. Autosave/Ctrl+S — SaveCoordinator с упорядоченными ревизиями
и ACK после commit; pending/dirty/saving/error/draft видимы. Safe close/switch,
backup/restore с checksum/inventory. S4 сохраняет полный неизменяемый снимок для
целевой ревизии и записывает изменённые агрегаты по [ADR-004](adr/004-sqlite-save-protocol.md).
Резервное копирование остаётся синхронным с пределом 4 ГиБ.

Targeted batches после блоков, полный pytest/Ruff/pip/diff/architecture gate после
стабилизации; source/frozen Windows smoke, source parity, manifest/CRC/SHA, лицензии.
[Архитектура](architecture/LODANDSY.drawio), [приёмка](../build_support/README.md),
[итоговая проверка](validation/2026-11-20-iteration-7.md).
Нативный Qt render/test не заменяет физический монитор. Clean Windows без Python,
ручная визуальная/multi-display/mixedDPI приёмка этой сборки остаются отдельными
результатами владельца; ARU-64 не закрывается по smoke на машине с Python.

## Утверждённое дополнение Cards / Actors / Variables / 5e14

Пакет владельца 21.11.2026 R01–R10 заменяет прежнее откладывание формул,
индивидуальных inventory и состояний. ADR-033 и validation report фиксируют реализацию.
Card — база без обязательного размещения; Actor — сохранённое имя/состояние, UUID и
inventory, принадлежащие Card; Token — размещение. Character/Creature/Object имеют
Actor, остальные типы сохраняют Card-only placements. Все 12 типов и immutable type
сохраняются. Player при новом размещении/копии использует выбранного основного Actor;
NPC/Object создают нового с template inventory и current=effective max либо unknown.
Toggle Player предупреждает и требует выбора existing/new, не меняет старые refs.
Удаление последнего token/map/layer сохраняет Actor. Actor/Card удаляются явно с
перечнем зависимостей. Во «Связях» видны и участники без размещений.

«Открыть инвентарь» в контекстном меню токена открывает существующую таблицу
по `Actor.inventory_id`. Плавающее окно «Инвентарь — [имя участника]» повторно
используется для всех размещений этого Actor. Изменения строк, экипировки
и кошелька видны во всех представлениях таблицы. Если у участника нет инвентаря,
команда недоступна. При удалении Actor его окно закрывается. При смене мира
окнами управляет раскладка проекта.

«Характеристики»: явный выбор базы или участника, current/temp HP и индивидуальные
final overrides, отдельно read-only effective/auto/source/dependencies. Inspector Card
технический; Token/Actor Inspector сохраняет оперативные поля карты. Native Card
Editor layout/QTextDocument/UUID/Undo/drafts сохраняются. Скорость хранится в ft,
метры и клетки вычисляются по известному feet_per_cell карты. HP абсолютные целые≥0,
процент производный. При росте max current не лечится, при снижении ограничивается
атомарно; null не становится 0. Невалидные и конфликтные drafts не становятся каноном.

Каталог: scores default10, level/XP, шесть modifiers/saves, proficiency1–20, 18skills
с proficiency/expertise, passive Perception±5, initiative, scalar weapon/spell inputs,
AC без/лёгкая/средняя/тяжёлая броня и один shield, speed и carrying Small/Medium.
HP auto: только сохранённая single-class die history с корректным полным первым die;
недостаточные входы unknown, multiclass и история с minimum-edge unsupported/manual.
CR auto, class features, other movement, slots/remaining hit dice, attunement,
полноценные conditions/combat/расход/отдых не реализованы и не выдаются за расчёт.

Item modifiers редактируются во вкладке «Модификаторы»: set/multiply/add/minimum/maximum, stable UUID,
явная stacking group/policy/priority. Активность — ручное заявление GM. Индивидуальный
inventory клонируется один раз с новыми row/column UUID и общими Item refs; Item cost/
description проецируются live. Qty влияет на вес, не множит бонус; удалённый Item
остаётся soft ref, неполные значения диагностируются. Новые источники расширяют тот же
контракт, без effects engine. Нет глобального equipped на Item Card.

Проектные формулы — раздел единого нативного окна настроек из шестерёнки правого rail: локальный draft, пример,
preview/ошибки/ожидаемые HP clamps, явные apply/reset. Без eval/exec/исполнения AST;
ограниченные грамматика/типы/DAG/бюджеты ADR-033. Manual HP/AC/speed — итоговый override,
auto остаётся видимым. Shipped defaults неизменны, overrides/revision — один канон.

Составные изменения валидируются до post-commit; SQLite16 нормализует Actors/tokens/
default/rules, один snapshot writer и durable ACK. Schema14 и старые payload безопасно
отклоняются без автоперезаписи. Backup/restore сохраняют UUID/rules/manual/activity.
Undo/Redo размещения/копии/движения адресован, preflight до смены индекса; последующие
HP/inventory/rules не откатываются. Creation inverse с новыми зависимостями блокируется.
Scalar/deletion Undo, перенос NPC между картами и другие rulesets вне этого пакета.

Приёмка: T01–T29 и физический checklist в validation report/build_support/README.
Только проверенный целостный кандидат; чистая Windows/два монитора/mixed DPI остаются
отдельными физическими проверками, не заменяются pytest или программным smoke.

Исправление UI-приёмки A–F: ADR-034; виртуальные `system:attributes`/`system:modifiers`
без Section/миграции. Ресурсы сверху, плитки модификатор (итог), база и источники,
адаптивные 3/2/1 блоки (ADR-035). Русские UI labels/choices/errors без перевода канонических ID.
История хитов по уровням, закрытый каталог целей модификаторов, typed rule examples,
табличный preview до/после и clamp; закрытие несохранённых правил подтверждается.
Ручная приёмка U01–U18 относится к новому ZIP; прошлый пакет её не заменяет.


Дополнение 22.11.2026 — лист персонажа v2 / ADR-035: inline ability scores, 3/2/1
блоки с 18skills/6saves, homebrew race/class/subclass/level. Item equipment facts
определяются только active inventory rows, один armor/shield с atomic replace/cancel.
Card armor_type/armor_base/shield удалены; это только resolved formula inputs.
Исторический формат шага SQLite16/Card7, профиль5e14 version2. SQLite15 отклоняется
без записи/удаления. Действующая политика совместимости изложена в ADR-040.
Ручной итоговый AC побеждает, оборудование и источники видны в native AC dialog.
Отчёт: docs/validation/2026-11-22-character-sheet-v2.md. Новые Git-публикации не разрешены.

## Maps M5 — согласовано25.11.2026

ARU-87–90 / ADR-036: расстояние при drag (сетка5e14 и геометрия), постоянные
публичные фигуры поверх fog, GM-only порталы с retarget существующего Player и
временный синхронный показ original token asset. Фигуры не раскрывают карту/токены;
стрелки публикуются только при полностью открытом пути. Нет боя/LOS/Actor transfer.
SQLite16/Card7, Map8 с безопасным чтением Map7 без записи на open. Критерии D/S/P/V/G,
проверки и физические ограничения: docs/validation/2026-11-25-map-m5.md.


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

## Tools T3 / ARU-92–96

В окне настроек проекта доступны стандартные валюты D&D 5e 2014 и настраиваемые
номиналы, а также пользовательские категории Item. У Item есть цена с номиналом,
вес и флаг допуска к луту. Кошелёк шаблона и каждого Actor редактируется в
строках инвентаря. Enter, Tab и потеря фокуса подтверждают допустимое количество,
Escape отменяет текущий ввод. Player использует общий кошелёк своего Actor на разных картах.

Резервное копирование и восстановление доступны в отдельных разделах окна
настроек как явные команды. Визуальные требования описаны в
[стандарте интерфейса](design/UI-SYSTEM.md).

В меню «Инструменты» доступны генератор лута и магазин. Лут соблюдает диапазоны
количества и стоимости, включает монеты и фиксирует выбранные позиции. Результат
копируется с UUID и вставляется в инвентарь одной операцией. Магазин показывает
временную выборку уникальных Item и их текущие цены. Последний результат каждого
инструмента восстанавливается из раскладки соответствующего мира.

SQLite17 открывает проекты T3. Файлы SQLite16 отклоняются без изменения.
[ADR-039](adr/039-tools-t3-economy-inventory.md) ·
[Проверки и поставка](validation/2026-11-26-tools-t3.md).
