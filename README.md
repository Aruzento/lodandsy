# LODANDSY

Локальное Windows-приложение ведущего: независимые Card/Map/Table документы,
общий Tree, Inspector и Dice. Python3.14.8 / PySide6 6.11.2 / Qt ADS5.1.1,
pyvips3.2.0 + pyvips-binary8.18.7; Qt Widgets без web runtime.

Итерация7: [требования A–G](docs/iterations/2026-11-20-iteration-7/CODEX-ITERATION-7.md),
[действующий MVP](docs/MVP.md), [архитектура draw.io](docs/architecture/LODANDSY.drawio),
[проверки/ограничения](docs/validation/2026-11-20-iteration-7.md),
[финальная стабилизация](docs/validation/2026-11-20-iteration-7-stabilization.md),
[сборка и ручная приёмка](build_support/README.md). План/состояние — существующие задачи Linear.

Cards/Tables/Maps/Dice сохраняют отдельных владельцев ADR-027. Composition root
связывает публичные контракты, Core/Resources/Media/Navigation и атомарные ProjectActions.
Один канон EntityCollection/SQLite14/Card5/Map6/Table3, assets отдельно, UI state4.
Legacy не адаптируется: несовместимый мир отклоняется без записи; пользовательские
проекты автоматически не удаляются. MOW importer/source fields удалены.

Нормальный старт — Welcome с MRU известных миров, без автоматического открытия.
Open показывает каталог title/path; другая папка, locate и удаление только записи —
вторичные действия. QSettings identity LODANDSY/LODANDSY вне мира/backup, история
только успешных create/open/restore. Backup/restore — gear правого rail, без дублей меню.

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
Новый Map имеет «Слой1», grid default opacity0.25, Token ПКМ — OpenCard/DeleteToken.
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
python -m build_support.package_windows --archive LODANDSY-Iteration7-Stable-2026-11-20.zip
```

Build использует requirements-build.lock, лицензии/источники входят в portable ZIP.
Private references, пользовательские миры и .prototype-deps в source bundle не входят.
Git — только в конце после финальной проверки по последним указаниям владельца.
