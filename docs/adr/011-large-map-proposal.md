# ADR-011 — крупные растровые карты: принятая архитектура

19.11.2026, ARU-70. **Принято владельцем после Windows-прототипа.** Владелец явно
разрешил pinned зависимости и production-пирамиду при сохранении S3/assets/MapPin,
ограничении ресурсов, отмене, crash recovery и проверке реальных изображений/поставки.

## Контекст и сравнение

M1 хранит исходный asset, MapPin — нормализованные координаты; Qt загружает полную
QImage/QPixmap с лимитом16MP/64MiB. Просто поднять предел небезопасно.
Сравнены Qt6.11.2 ClipRect и libvips8.18.7 через pyvips3.2.0/pyvips-binary8.18.7.
Прототип полностью отделён в `.prototype-deps/map-preflight-venv`; на этапе сравнения
production не менялся. После согласования pyproject/lock обновлены, production MapView
использует только visible tiles. SQLite, Markdown и Qt ADS остаются прежними.

Измерение: Windows10 build19045, Python3.14.8 x64, 12 logical CPUs, 31.37GiB RAM.
CPU model недоступна из-за прав CIM, поэтому не приписывается. PNG — синтетический
цветной raster, созданный потоковым генератором; это не замер реальной карты владельца.
Peak RSS опрашивается psutil каждые10ms, значения включают интерпретатор/библиотеки.
Рабочие процессы отдельные; точность пиков ограничена частотой измерения.

| Вариант | Вход | Результат | Время | Peak RSS |
|---|---|---|---|---|
| Qt ClipRect256×256, default allocation256MiB | 100MP PNG | отказ, ClipRect unsupported | 0.109s | 38.62MiB |
| Qt ClipRect256×256, allocation512MiB только в прототипе | 100MP PNG | участок256×256 | 0.636s | 419.62MiB |
| Qt ClipRect256×256, default allocation | 25MP PNG | участок256×256 | 0.194s | 124.26MiB |
| libvips sequential dzsave, concurrency2/cache32MiB | 100MP PNG | полная pyramid256px PNG | 4.119s | 75.69MiB |
| libvips, те же параметры | 25MP PNG | полная pyramid | 1.349s | 55.09MiB |
| frozen libvips exe | 100MP PNG | полная pyramid | 4.469s | 92.34MiB |
| frozen Qt6.11.2 + ADS5.1.1 + libvips | 1100×700 | manager создан, pyramid создана, Qt прочитал tile/pixel | 0.081s | 65.34MiB |

Qt обрабатывает участок быстрее, но для PNG сначала выделяет память всего изображения.
Этого недостаточно для безопасного универсального large-raster renderer. libvips
строит все уровни один раз; RAM существенно меньше полного raster. 100MP source
10,025,104bytes, derived pyramid2148files/323,836,171bytes: disk overhead измерен,
не выводится из encoded size. На JPEG/WebP/реальных картах нужны отдельные измерения.

## Предлагаемое решение

1. Добавить закреплённые pyvips3.2.0 и pyvips-binary8.18.7 (cffi как dependency).
   Worker изолировать в отдельном процессе: отмена/timeout/лимит памяти не должны
   завершать GUI. На Windows использовать JobObject и завершение worker при закрытии.
2. Исходный immutable asset остаётся каноническим. Cache `map-tiles-v1/<source-sha>/`
   содержит derived manifest и DeepZoom pyramid256px PNG без overlap. Никаких новых
   canonical SQLite полей для E. Temp staging публикуется rename после успешной
   проверки; прерванный staging не читается. Missing/cache-version mismatch → rebuild
   из source; cache не входит в backup. Удаление source диагностируется без потери pins.
3. В GUI только видимые tiles подходящего LOD: общий LRU64MiB и ограниченная очередь.
   Нет полной QImage/QPixmap карты. Scene world units — пиксели исходного raster;
   M1 pins продолжают преобразовываться из нормализованных координат. Zoom/DPI/LOD
   не изменяют domain coordinates. Inspector/Tree/ADS не зависят от decoder backend.
4. Долгий импорт имеет progress/cancel, проверяет signature/loader, размеры, disk budget
   и доступное место, bounded decoding в worker. PNG/JPEG/WebP — streaming path.
   Legacy BMP/GIF должны остаться читаемыми; если loader не потоковый, используется
   прежний bounded raster path в worker, с явной диагностикой ресурсоёмких файлов.
   Не обещается бесконечный размер или произвольный повышенный pixel limit.
5. До объявления E выполненным: измерить реальные pan/zoom/cache/RAM, несколько карт,
   cancel/crash/rebuild, старыйM1/backup/restart и новый Windows package. F начинается
   только после реализации и проверки E. ARU-64 остаётся gate чистой Windows без Python.

## Зависимости, лицензии, поставка

Проверены CPython3.14.8, cffi2.1.1, pyvips3.2.0, pyvips-binary8.18.7, PyInstaller6.22.3,
PySide6/Qt6.11.2, ADS5.1.1 в одном отдельном venv. Frozen compatibility smoke имеет
exit0; использует bundled `_libvips.pyd`/19,018,240byte DLL. Python установлен на
проверочной машине; это не clean-machine acceptance. PSUtil7.2.2 нужен только метрикам.

pyvips — MIT. Binary distribution metadata — LGPL-3.0-or-later, wrapper LICENSE — MIT;
DLL содержит libvips и зависимости с собственными лицензиями. В поставку потребуется
включить aggregate notices, тексты лицензий, версии/исходники и возможность замены
DLL/пересборки. Полная production inventory и упаковка — часть E после согласования,
не объявлены завершёнными прототипом. Собственную лицензию приложения это не выбирает.

Первичные источники:
- [Qt QImageReader, ClipRect/ScaledSize](https://doc.qt.io/qt-6.11/qimagereader.html)
- [libvips pyramid builder](https://www.libvips.org/API/current/making-image-pyramids.html)
- [pyvips binary install](https://libvips.github.io/pyvips/README.html)
- [binary packaging](https://github.com/kleisauke/pyvips-binary)
- [aggregate third-party notices](https://github.com/kleisauke/libvips-packaging/blob/main/THIRD-PARTY-NOTICES.md)

Пересмотр: несовместимая frozen сборка/лицензионная поставка, неприемлемые затраты cache,
memory/latency на целевом оборудовании или новые утверждённые форматы. Альтернатива
Qt-only возможна при сужении больших форматов до подтверждённых bounded handlers;
для текущего PNG-контракта прототип не подтвердил её пригодность.

## Реализация и измерения production E

Принятый вариант реализован в application/map_pyramid.py, map_pyramid_worker.py,
map_tiles.py, module_controller.py и ui/map_widget.py. Один тяжёлый процесс, Windows
JobObject512MiB (реальный MemoryError проверен тестом), timeout900s, cancel/parent-death
watch. Windows venv redirector исключён из цепочки запуска: terminate попадает в сам
decoder. Windowed frozen worker восстанавливает inherited stdout/stderr pipes;
автоматический smoke проверяет промежуточный progress, а не только итог100%.

Source budget2GiB, derived disk budget4GiB с расчётом RGBA8 pyramid +4KiB/tile,
не более32768tiles; учитывается свободное место. 16-bitPNG превращается в8-bit только
в display cache; source остаётся побайтно прежним. Legacy BMP/GIF — Qt в worker,
до16MP. GUI tileLRU64MiB/pending64, image≤256px, один painter рисует только viewport.
SHA source проверяется перед использованием готового кеша и после нового decode.
Manifest v1 публикуется последним в staging, проверяются все ожидаемые tiles;
целая директория становится ready через rename. Неполный кеш и версия, отличная от1,
перестраиваются. Плохой tile инвалидирует manifest с диагностикой; reopening rebuilds.
Source/target/staging paths проверяются независимо и в worker. Assets не очищаются.
Удаляется только собственный derived staging/заменённый invalid cache. После crash
оставшийся staging не является ready и не читается. Backup содержит source, не cache.

На том же Windows hardware production benchmark, **два независимых окна**,80pan/zoom
кадров с реальным tile loading, save и повторное открытие:

| Вход | Размер | Import + open | Cached reopen | GUI RSS peak | Worker RSS peak | Render p50/p95 |
|---|---|---|---|---|---|---|
| Synthetic PNG10000² | 10,025,104B | 10.247s | 2.047s | 168.38MiB | 78.98MiB | 23.80/27.82ms до viewport fix |
| NASA JPEG21600×10800 | 29,698,041B | 17.758s | 4.861s | 162.52MiB | 164.30MiB | 0.97/1.30ms |
| NASA тот же raster PNG | 257,528,839B | 24.844s | 5.017s | 161.73MiB | 117.57MiB | 1.03/1.53ms |

NASA измерения — **после** исправления обхода невидимых tiles, максимум30tiles/frame,
cache ровно64MiB; наибольший GUI timer gap28.78/29.63ms. Это замер автоматического
render, не субъективная ручная оценка плавности, DPI или гарантированный SLA. Последняя
проверка SHA в конце нового decode добавлена после замера; время import может отличаться.
Источник реального изображения: [NASA January Blue Marble](https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-topography-bathymetry/),
JPEG из assets.science.nasa.gov, авторы/credits на исходной странице. PNG преобразован
потоково только для теста encoded file>64MiB. Файлы не входят в приложение/репозиторий.
Прототип воспроизводится `python -m prototypes.map_runtime_benchmark SOURCE --report FILE`.

Full frozen Windows app smoke проходит (Cards/Maps/Tools/S3/layout/backup/restart,
worker intermediate progress). Native libvips DLL SHA совпал с официальным архивом:
06dab07cc386748513337a31672b1d5269fbc770a14ff403080575665bf0813f.
Versions/provenance/aggregate notices/LGPL/MIT/BSD добавлены в build_support/licenses,
packager проверяет hash перед поставкой, добавляет source и инструкции замены DLL.
Кандидат локальный, не публичный release. Native UX принят владельцем 19.11.2026;
[запись приёмки](../validation/2026-11-19-owner-acceptance.md). Clean-Windows без
Python остаётся открытой в ARU-64. Никакой новой схемы canonical data в E нет.

Итоговая регрессия: источник с опасным PNG header отклоняется до публикации;16-bitPNG
display cache переводится в uchar **и**8-bit interpretation (иначе pngsave повышал
разрядность обратно). Проверены точный цвет и неизменность source. Проверен реальный
Windows junction escape для assets/cache; отдельный file symlink остаётся недоступен
тестовому аккаунту. При следующем открытии убираются до16завершённых аварией staging
директорий строго внутри reserved cache path; canonical assets не удаляются.
LOD учитывает deviceTransform/DPI, при экстремальном viewport выбирается более грубый
уровень для≤128tiles/frame. Zoom minimum зависит от fit, сохраняется камера узких
больших raster. Pending load не записывает фиктивную камеру; закрытые camera preferences
сохраняются как UI DTO, restore готовой карты не маскирует последующий pan/zoom.

Карты с одинаковыми исходными байтами переиспользуют проверенный immutable asset по SHA,
сохраняя независимые MapDocument/geometry. Общий прежний backup/restore budget4GiB
SQLite+assets теперь проверяется и при backup: архив, который restore не примет,
не публикуется, предыдущая копия сохраняется. Cache в budget не включён. Расширение
этого storage-профиля и асинхронный backup/restore — дальнейшая работа: крупные архивы
пока задерживают UI. Профиль real233MP+несколько карт проверен в пределах этого budget.
