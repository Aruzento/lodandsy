# LODANDSY

Локальное Windows-приложение ведущего: независимые Card/Map/Table документы,
общий Tree, Inspector, Dice, генератор лута и магазин. Python3.14.8 / PySide6 6.11.2 / Qt ADS5.1.1,
pyvips3.2.0 + pyvips-binary8.18.7; Qt Widgets без web runtime.

Итерация7: [требования A–G](docs/iterations/2026-11-20-iteration-7/CODEX-ITERATION-7.md),
[действующий MVP](docs/MVP.md), [архитектура draw.io](docs/architecture/LODANDSY.drawio),
[проверки/ограничения](docs/validation/2026-11-20-iteration-7.md),
[финальная стабилизация](docs/validation/2026-11-20-iteration-7-stabilization.md),
[сборка и ручная приёмка](build_support/README.md). План/состояние — существующие задачи Linear.

Пакет Cards/Actors/Variables/5e14: [ADR-033](docs/adr/033-actors-variables-and-5e14.md),
[инженерный отчёт и T01–T29](docs/validation/2026-11-21-cards-actors-5e14.md).
Card хранит общую базу, Actor — индивидуальные HP/имя/инвентарь, Token — размещение.
Player при новых размещениях использует выбранного Actor; NPC/Object создают
независимых участников. Удаление размещения сохраняет участника во вкладке «Связи».
Вкладка «Характеристики» редактирует базу или явно выбранного участника; инвентарь участника открывается
отдельной Table. Активные Item modifiers пересчитывают зависимости, quantity не множит
бонусы. Ручные HP max/AC/speed имеют окончательный приоритет.
Формулы проекта открываются из шестерёнки справа («Игровая система и правила…»), проверяются и применяются явно; shipped
формулы остаются доступны. Только 5e 2014: не заявляются полный бой, multiclass HP,
слоты заклинаний/остатки Hit Dice, условия эффектов или конструктор новых переменных.
Старые SQLite14/15 безопасно отклоняется без миграции и перезаписи.

Исправление непройденной UI-приёмки: [ADR-034](docs/adr/034-native-game-sheets-and-russian-ui.md),
[отчёт A–F / U01–U18](docs/validation/2026-11-21-ui-acceptance-fix.md),
[матрица доступности полей](docs/validation/2026-11-21-ui-fields.md).
Inspector карточки оставляет технические свойства; оперативный Inspector карты — состояние
участника. Item имеет компактную вкладку «Модификаторы» с типизированной формой.
Системные страницы не добавляют Section и не меняют формат SQLite16/Card7/UIstate4.

Cards/Tables/Maps/Dice сохраняют отдельных владельцев ADR-027. Composition root
связывает публичные контракты, Core/Resources/Media/Navigation и атомарные ProjectActions.
Один канон EntityCollection/SQLite17/Card8/Map9/Actor1/Rules1(profile2)/Table4/Economy1, assets отдельно, UI state4.
v0.01 фиксирует базу совместимости. Последующие версии обязаны безопасно мигрировать
поддерживаемые миры. Неподдерживаемые прототипы и неизвестные будущие версии
отклоняются без записи. MOW importer/source fields удалены.

Welcome перечисляет миры в системном `Документы/LODANDSY/project/` без
автоматического открытия. Создание и восстановление запрашивают только имя.
Существующий мир из другого каталога можно открыть явно. История успешных открытий
хранится в QSettings вне мира. Backup/restore доступны из окна настроек.
[ADR-040](docs/adr/040-managed-projects-v001.md)

Card Editor: крупный portrait слева132–220px, справа immutable type badge/title/
inline summary; отдельная строка tabs и контент с общим inset16px. Нет breadcrumb,
summary popup или центрированной узкой колонки. Шапка стабильна при загрузке,
переключении5карточек, вкладок и ширины. UUID sections сохраняют QTextDocument/Undo;
metadata update не прячет active embedded Table editor. Crop идемпотентен.

Table inventory — item UUID, positive integer quantity и живые description/cost,
без копирования derived cells. Semantic input commit Enter/Tab/blur/Escape/Ctrl+S;
конфликтный raw draft переживает reopen и не перезаписывает канон. UseSaved/ApplyMine
доступны в Card/Inspector/embedded и standalone Table, третья правка требует
повторного разрешения. Invalid draft не блокирует валидный autosave.
Cancel старого редактора сохраняет чужой более новый draft, включая semantic flush.
URI — только lodandsy://entity/UUID; контролируемый HTML/asset security ADR-014 сохраняются.

Map Viewer/Editor/Presentation читают один MapDocument/Undo и shared tiles/media.
Новый Map имеет «Слой1», grid default opacity0.25, Token ПКМ — OpenCard/CopyToken/DeleteToken.
Object Cards — original aspect/alpha long-edge128. Viewer monitor открывает один
отдельный player window; F11/double-click fullscreen, Escape выход, camera следует
Viewer с letterbox. Первое открытие сохраняет GM focus. Player read-only и не входит
в ADS/layout; до coherent map/fog/camera показывает только чёрный экран.

Ручной vector fog: brush/erase/polygon/select/delete, один жест — один Undo;
regions UUID/числовые rings сохраняют holes/splits в SQLite. GM alpha50%, player100%
black foreground над grid/objects/tokens. Provisional erase не раскрывает карту.
Нормализованная render geometry компилируется один раз на открытый map snapshot;
общий bounded cache не является вторым каноном. ADR-030/031/032.

Libvips: source≤2GiB/cache≤4GiB/32768tiles/worker≤512MiB/900s/shared tileLRU64MiB.
Full snapshot writer и synchronous backup≤4GiB сохраняются; это известные ограничения.
Clean Windows без Python, физический второй монитор/mixedDPI и визуальная приёмка
новой сборки учитываются отдельно от Qt render/автоматического smoke. Public release нет.

## Подготовка и запуск

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install --no-build-isolation --no-deps -e .
python -m lodandsy.main
# Явный путь обходит Welcome:
python -m lodandsy.main "D:\Миры\Мой мир"
```

## Проверки и сборка

```powershell
python -m pytest
python -m ruff check .
python -m pip check
git diff --check
powershell -File build_support/build_windows.ps1 -Python .venv/Scripts/python.exe -SkipPackage
python -m build_support.package_windows --archive LODANDSY-Character-Sheet-v2-2026-11-22.zip
```

Build использует requirements-build.lock, лицензии/источники входят в portable ZIP.
Private references, пользовательские миры и .prototype-deps в source bundle не входят.
Git — только в конце после финальной проверки по последним указаниям владельца.


Дополнение 22.11.2026 — лист персонажа v2 / ADR-035: inline ability scores, 3/2/1
блоки с 18skills/6saves, homebrew race/class/subclass/level. Item equipment facts
определяются только active inventory rows, один armor/shield с atomic replace/cancel.
Card armor_type/armor_base/shield удалены; это только resolved formula inputs.
SQLite16/Card7, профиль5e14 version2; legacy/миграции отсутствуют по новому прямому
решению владельца «все миры тестовые». SQLite15 отклоняется без записи/удаления.
Ручной итоговый AC побеждает, оборудование и источники видны в native AC dialog.
Отчёт: docs/validation/2026-11-22-character-sheet-v2.md. Новые Git-публикации не разрешены.

Полировка 25.11.2026: docs/validation/2026-11-25-polish.md; новый кандидат
LODANDSY-Polish-2026-11-25.zip. SQLite16/Card7 и принятые игровые контракты сохранены.

Maps M5: docs/validation/2026-11-25-map-m5.md; ADR-036. Фигуры поверх fog,
порталы, расстояния и original-image presentation. Новый кандидат LODANDSY-Map-M5-2026-11-25.zip.


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

## Экономика и инструменты T3

Шестерёнка справа → «Экономика проекта…». Здесь выбираются валюты и категории
предметов. На карточке Item во вкладке «Модификаторы» настраиваются цена, вес,
категория и допуск к генерации лута. Кошелёк расположен над строками инвентаря.

В меню «Инструменты» откройте «Генератор лута» или «Магазин». Лут можно
скопировать и вставить Ctrl+V в таблицу инвентаря. Добавление монет подтверждается
отдельно. Для T3 создайте новый мир. Схема SQLite16 отклоняется без записи.
[ADR-039](docs/adr/039-tools-t3-economy-inventory.md) ·
[Отчёт, снимки и приёмка](docs/validation/2026-11-26-tools-t3.md).
