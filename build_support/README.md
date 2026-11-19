# LODANDSY — Windows-кандидат итерации 4

Распакуйте всю папку LODANDSY на Windows10/11 x64 и запустите LODANDSY.exe.
Python/Qt/ADS/libvips встроены в _internal; exe отдельно не переносится.
Мир создавайте отдельно: project.sqlite3 + assets — данные, .lodandsy-ui.json — UI,
.lodandsy-cache — перестраиваемые tiles. Публичного release нет.

Текущий формат SQLite11/Cardv3/Mapv4/Tablev2/Dicev2. Старые тестовые проекты отклоняются
без записи; миграции/legacy редакторы отменены владельцем. Единственный URI entity/UUID.
Именно этот кандидат требует новой приёмки; прежний W2 preflight уже принят.

## Чек-лист десяти сценариев

1. Canon/Inspector: создать Card пяти компоновок, отдельно сменить тип/шаблон, title/summary/
   tags/aliases/характеристики,0/false/unset. Изменять в Card и Inspector, сохранять/reopen.
   Невалидное поле подсвечено и блокирует save до исправления/отмены, не теряется при close.
2. Design: hero и портрет рядом на широком окне/один столбец на узком, контекстный alt/caption/
   replace/remove; несколько секций description/history/notes/inventory с независимым Undo/
   курсором/scroll. Compact toolbar, secondary «Формат», все клавиатурные действия работают.
3. Mixed Tree/links: Card/Map/Table/Dice nesting/reorder/root, cycle refusal, скрытый поиск,
   «+» меню, дочерние через context. Copy URI/HTML, Ctrl+click открывает/фокусирует цель;
   source остаётся. HTTP(S) по клику, нет загрузки network images/file/javascript resources.
4. Card→tokens: одну Card с портретом разместить drag из Tree дважды и на второй карте;
   Tree не меняет parent. Title/portrait/HP менять без переименования: все экземпляры обновлены.
   Label/image/kind override явен и сбрасывается. Double click фокусирует Card. Удалить размещение
   — Card остаётся; удалить Card — warning с числом всех размещений, подтверждённый cascade;
   Undo карты не воскрешает Card/удалённые размещения. Broken ref диагностируется.
5. Geometry/grid: character круг+white frame, item alpha/aspect fit без рамки;1×1/2×2/3×3,
   snap/offset/cell size. Drag/repaint/pan/fractional zoom не утолщает grid, far LOD тонкий;
   светлый/тёмный фон, исходные центры/математический шаг сохраняются.
6. Map editor: «Редактировать карту»,2слоя, импорт decor один раз/много placements, существующий
   asset, move/resize/rotation/z/delete/Undo/Redo. Layer visibility/order/rename сохраняются;
   nonempty delete подтверждается, hidden не уничтожает. Вернуться к tokens без чужих drag.
7. MOW: Проект→Импорт файла/каталога, выбрать source и узел назначения; preview/report до apply,
   skip повторных UUID либо явный remap. Реальный sample: folder «Существа.Тюрьма - подземка»,
   пустые body/portrait, missing parent warning. Runtime controls отсутствуют. Поддержанный
   local img src и .wiki-link[data-page-id] переносятся; data-asset без manifest диагностируется.
   Cycles/duplicate/bad YAML не публикуются частично. Source не изменён.
8. Media/large map:20разных inline images, прокрутить до каждого и обратно/close/reopen,
   missing/corrupt placeholder, image delete/Undo. Карты PNG/JPEG/WebP большие,2окна/1000tokens,
   layers/objects, cancel/error/rebuild cache. Ресурсы bounded, фон не декодируется целиком в GUI.
9. Tools/save: typed Table text/number/bool, invalid draft/correction/copy/atomic TSV/random row;
   0/false не пусты. Dice d4…d100, mixed throw/каждый результат/сумма/повтор/copy/пресеты.
   Одновременно Cards/Map/Table/Dice, autosave/Ctrl+S→перезапуск: те жеUUID/поля/ссылки/layout.
   Backup вне мира→restore в новую папку, ресурсы/слои/MOW сохраняются, tiles строятся заново.
10. Native/frozen: dock all sides/center/insert/float/redock, maximize→drag без прыжка,
    локальный focus/Ctrl+Z, узкие окна/клавиатура,2монитора/mixedDPI/отключение монитора.
    Именно новый ZIP проверить на чистой Windows без Python и в кириллическом пути.

## Ограничения и воспроизведение

Backup/restore пока синхронны,≤4GiB суммарно без tile cache (ARU-54); cancellation/progress
для них только следующий контракт. Source map≤2GiB, cache≤4GiB/32768tiles, worker≤512MiB/900s,
tileLRU64MiB, BMP/GIF≤16MP. Raster Card/decor≤64MiB/32MP, thumbnail≤1024, documentLRU8MiB,
sharedmedia16MiB/32pending. MOW import≤500файлов/2MiBкаждый/64MiBсуммарно, v1 subset.
Эти пределы не являются SLA. Полный snapshot writer остаётся; incremental SQL не реализован.

Автоматический smoke во временном мире (не ручная приёмка):

```powershell
.\LODANDSY.exe --self-test --report "$env:TEMP\lodandsy-smoke.json"
```

Для реального большого фона: --large-map-image "C:\Maps\large.jpg".
Source: source/MANIFEST.sha256, ZIP SHA256 — соседний .zip.sha256.

Пересборка Windows x64: CPython3.14.8, PySide6/Qt6.11.2, ADS5.1.1,
pyvips3.2.0/binary8.18.7. Новых runtime зависимостей итерация4 не добавляет.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.lock
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pip check
.\build_support\build_windows.ps1 -Archive LODANDSY-Iteration4-2026-11-19.zip
```

Лицензии/source/provenance в THIRD-PARTY.md и LICENSES. Qt LGPL/GPL texts должны находиться
в .prototype-deps/license-texts; libvips hash проверяется сборщиком. ICU Windows, без лишней
ICU78. При смене dependencies повторять compatibility/license/preflight. Commit/push/merge/
release требуют нового отдельного разрешения владельца.
