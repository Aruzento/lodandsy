# LODANDSY

Локальное Windows-приложение ведущего: независимые документы, общее дерево и инструменты.
Python3.14 / PySide6 6.11.2 / Qt ADS5.1.1. ADS размещает окна, WindowManager управляет жизнью.

Итерация5: [MVP](docs/MVP.md), [пакет A–G](docs/iterations/2026-11-19-iteration-5/CODEX-ITERATION-5.md),
[фактические проверки](docs/validation/2026-11-19-iteration-5.md),
[визуальный контракт](docs/design/iteration-5-layout.md). План и статусы — Linear.

Дерево Card/Map/Table. «+» раскрывает создание, поиск под кнопкой/Ctrl+F, дочерние через
контекст. Card имеет только тип и UUID-вкладки: визуальный текст либо ссылка на дочернюю
Table. Инвентарь персонажа — одна настоящая дочерняя таблица. Характеристики только в
Inspector. Hero/портрет с crop, отдельный Undo каждой rich-вкладки, scoped hotkeys.
Ширины боковых областей меняются native разделителями и сохраняются с раскладкой.

Map viewer и самостоятельный Map Editor — два окна одного канона/Undo/tiles с разными
камерами. Viewer управляет токенами Card, editor — слоями/raster objects и преобразованиями.
Свободное движение без snap; grid в общих world coords. Большие карты — libvips worker и
перестраиваемая пирамида, без полного background QPixmap в GUI. Source≤2GiB,
cache≤4GiB/32768tiles, worker≤512MiB/900s, tileLRU64MiB, BMP/GIF≤16MP (ADR-011).

Table: text/number/bool, [+] после заголовков, контекст/drag порядка, atomic TSV и copy,
общие данные/drafts между окнами. «Инструменты → Кубики» — один tool:dice без Entity,
доступный без проекта: d4…d100, modifier, каждый результат/сумма/copy/history50 в сессии.

SQLite S3 — единственный канон, assets отдельно. SQLite12/Card4/Map5/Table2, UI state4.
Autosave/Ctrl+S — один revision writer. Invalid UI drafts помечаются отдельно и не мешают
сохранению допустимых данных. Close/switch предлагает исправить/отбросить draft/отмену.
Backup/restore≤4GiB пока синхронны; full snapshot writer сохраняется (отдельные работы).
Legacy Markdown/templates/tags/snap/Dice entity/random table mode удалены без адаптеров.
Неподдерживаемые проекты отклоняются без записи, тестовые разрешено пересоздавать.

Qt HTML whitelist, единственный URI lodandsy://entity/UUID через application layer.
HTTP(S) только по явному клику, network resources заблокированы, local images — только
assets с защитой выхода из директории. Media≤64MiB/32MP, bounded thumbnails/working set.
MOW v1 subset — read-only import preview → skip/remap → atomic apply, source metadata/
aliases/безопасные тексты/media/links сохраняются, исключённые данные отражены в отчёте.

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
[сборка/чек-лист приёмки23 пунктов](build_support/README.md).
Прежняя приёмка не покрывает новый вид/поведение. Clean Windows без Python (ARU-64),
физическая mixedDPI и визуальная приёмка владельца учитываются отдельно. Public release нет.
Git-действия только после итоговой проверки и разрешения владельца.
