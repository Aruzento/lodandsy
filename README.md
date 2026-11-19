# LODANDSY

Локальное Windows-приложение ведущего: независимые документы, общее дерево, карты и
инструменты. Python 3.14 / PySide6 6.11.2 / Qt ADS 5.1.1. Tree/Inspector фиксированы;
ADS размещает окна, WindowManager управляет жизнью.

Итерация 3: [контракт MVP](docs/MVP.md), [требования A–G](docs/iterations/2026-11-19-iteration-3/REQUIREMENTS.md),
[проверки](docs/validation/2026-11-19-iteration-3.md). План и статусы — Linear.

Одно смешанное дерево Card/Map/Table/DiceDocument без разделов. «+» раскрывает создание,
поиск скрыт под кнопкой (Ctrl+F); дочерние документы — через контекстное меню.
Enter/двойной щелчок открывает или фокусирует окно ID. Выбор меняет Inspector, сохраняя
контекст редакторов. Card — визуальный QTextEdit: шрифт/размер/цвет/списки/выравнивание,
ссылки/изображения/Undo. Формат — контролируемый Qt HTML. Только lodandsy://entity/UUID;
копирование ссылки даёт HTML fragment и plain URI. HTTP/HTTPS открываются по явной
активации; сетевые ресурсы заблокированы, локальные картинки — только assets проекта.
Импорт raster64MiB/32MP, bounded thumbnail, удаление ссылки не удаляет общий ресурс.

SQLite S3 — единственный источник данных, assets отдельно. Autosave/Ctrl+S используют
один writer с ревизиями и видимыми ошибками. Backup/restore до4GiB, UI state отдельно.
По решению владельца legacy Markdown, старые форматы/режимы/адаптеры, обязательные
миграции и архивирование отменены. Неподдерживаемый проект отклоняется без изменения
файлов; тестовые миры пересоздаются. Устаревшее сохраняется лишь при обоснованной необходимости.

Большие PNG/JPEG/WebP: ограниченный libvips worker и перестраиваемые тайлы (ADR-011).
Source2GiB; cache4GiB/32768tiles; worker512MiB/900s; GUI LRU64MiB. BMP/GIF bounded16MP.
Отмена/ошибка не публикует частичную пирамиду. Не заменять renderer полным QPixmap.

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
```

Windows: requirements-build.lock и build_support/build_windows.ps1;
[сборка и ручная приёмка](build_support/README.md). Прежняя приёмка не покрывает A–G.
Новая полная поставка без Python пока не проверена (ARU-64). Публичного release нет.
Commit/push/merge требуют отдельного разрешения.
