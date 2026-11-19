# LODANDSY

Локальное Windows-приложение ведущего: независимые документы, общее дерево и инструменты.
Python3.14 / PySide6 6.11.2 / Qt ADS5.1.1. ADS размещает окна, WindowManager управляет жизнью.

Итерация6-rev3: [MVP](docs/MVP.md),
[пакет A–E](docs/iterations/2026-11-19-iteration-6-rev3/CODEX-ITERATION-6.md),
[проверки и ограничения](docs/validation/2026-11-19-iteration-6.md),
[архитектура draw.io](docs/architecture/LODANDSY.drawio), ADR-027/028/029. План — Linear.

Cards/Tables/Maps/Dice имеют отдельных владельцев; composition root связывает общие
Core/Resources/Media/Navigation и атомарные ProjectActions. Один канон EntityCollection/
SQLite13/Card4/Map5/Table3, assets отдельно, UI state4. Прежние смешанные controllers/
sessions удалены. Домен без Qt/SQL. Legacy/старые тестовые форматы не адаптируются и
не перезаписываются. Реальные миры автоматически не удаляются.

Tree Card/Map/Table, «+» с меню, поиск под кнопкой/Ctrl+F, дочерние через контекст.
Graphite Qt Widgets: square portrait слева/metadata справа, breadcrumb/copy, prose≤760,
Table full width, сгруппированный Inspector, без отдельной прокрутки шапки. UUID-вкладки
rich text/child Table сохраняют независимый Undo; удалённые ресурсы очищаются адресно.
Crop идемпотентен, asset неизменяем, символы URI только lodandsy://entity/UUID.

Инвентарь — обычная дочерняя Table: item UUID/положительное quantity/живые read-only
описание и единичная стоимость. Проекции не копируются в SQLite. Reference picker с
title/aliases/path/UUID; недоступный item сохраняет ссылку/количество. Универсальные
Table types text/number/bool/entity_ref/projection, UUID headers, atomic writable TSV.
Semantic input commit Enter/Tab/blur, Escape, конфликт/draft без потери курсора/Undo;
Ctrl+S flush, единый autosave writer. Invalid draft не блокирует валидное сохранение.

Viewer/Editor карты — самостоятельные окна с общим MapService/Undo/tiles. Editor tool
rail/canvas/right layers/Object Card library/properties. Только Card(object) с main image;
import создаёт Card, размещение original aspect/alpha long-edge128 без portrait crop.
Front layer сверху, scoped Undo IconOnly. Card placements/cascade, свободный grid без snap.
Libvips: source≤2GiB/cache≤4GiB/32768tiles/worker≤512MiB/900s/tileLRU64MiB (ADR-011).

Кубики singleton tool:dice без проекта/Entity:7типов+modifier/result/copy/history50.
HTML/media security и read-only MOW import сохраняются. Backup≤4GiB пока синхронен,
full snapshot writer не заменён. Clean Windows без Python и physical mixedDPI требуют
отдельной приёмки новой сборки; прежний W2 preflight не покрывает новый UI.

## Подготовка и запуск

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install --no-build-isolation --no-deps -e .
python -m lodandsy.main
```

## Проверки

```powershell
python -m pytest
python -m ruff check .
python -m pip check
git diff --check
```

Windows: requirements-build.lock, build_support/build_windows.ps1 и
[сборка/чек-лист приёмки итерации6](build_support/README.md).
Прежняя приёмка не покрывает новый вид/поведение. Clean Windows без Python (ARU-64),
физическая mixedDPI и визуальная приёмка владельца учитываются отдельно. Public release нет.
Git-действия только после итоговой проверки и разрешения владельца.
