# LODANDSY — кандидат итерации 19.11.2026

Распакуйте всю папку LODANDSY на Windows10/11 x64 и запустите LODANDSY.exe.
Встроенные Python/Qt/libvips находятся в _internal; exe отдельно не переносится.
Мир храните в отдельной папке с project.sqlite3 и assets/. Кандидат локальный,
публичный release не опубликован. Новая сборка проверяется отдельно от MVP18.11.

1. Дерево «Проект»: «Карточки / Карты / Таблицы / Кубики». Верхний «+» раскрывает
   создание; поиск спрятан под кнопку (Ctrl+F). Enter/кнопка открытия/двойной щелчок
   открывают документ; «…»/ПКМ/Shift+F10 — действия. Дочерняя Card — через контекстное
   меню, у карточек нет «+». Выбор меняет Inspector, редакторы сохраняют контекст.
2. Создание Card: имя и шаблон (Пустая/Статья/Персонаж/Локация/Предмет). Source Markdown,
   preview/split, toolbar оформления, link/image, font/scale просмотра. Просмотр
   исходник не меняет. Изображение: файл/paste/drop, alt, копирование в assets.
   Undo сохраняет общий ресурс. PNG/JPEG/WebP/BMP/GIF≤64MiB/32MP для Card/token.
3. Карта из «+»/раздела: PNG/JPEG/WebP → progress/отмена → tile pyramid. Source≤2GiB,
   derived cache≤4GiB/32768tiles, decoder512MiB; BMP/GIF сохраняют bounded16MP path.
   Колесо — zoom, фон — pan, «Вся карта» — fit. ПКМ/«Маркер» добавляет прежний MapPin,
   его меню связывает с существующей/новой Card. Удаление Card оставляет broken link.
4. «Токен» или ПКМ на фоне: выберите картинку и название. Перетаскивание меняет world
   coordinates; ПКМ → свойства размера/порядка/связи, замена изображения, новая Card,
   open/unlink/delete. «Сетка…» — квадратные клетки в px карты, offset/opacity/show/snap.
   Snap — к центру клетки; смена сетки и zoom не передвигают существующие объекты.
   При очень мелком масштабе линии скрываются. Ctrl+Z/Ctrl+Y внутри карты — Undo/Redo.
5. «Кубики» в дереве: NdM±K, детали и сумма, повтор/копирование. «Таблицы»: создать,
   редактировать, менять порядок, выбирать случайную непустую строку, копировать.
6. Cards/Map/Tools — независимые документы Qt ADS: dock/float/tabs/split. Ctrl+S и
   autosave — один pipeline; ошибки/повтор видны в статусе. Закройте/откройте
   документы снова, сохраните проект и перезапустите программу.
7. «Проект» → backup/restore: backup вне мира, restore в новую папку. Старые S3 проекты
   мигрируются в schema4 с DB backup в backups/, assets не меняются. Старый executable
   schema4 не читает; для возврата используйте прежнюю копию проекта. Tile cache
   перестраивается из source после restore; его отсутствие не означает потерю карты.

Общий бюджет backup/restore —4GiB несжатых SQLite+assets. Backup заранее откажется,
если такой архив нельзя восстановить в поддерживаемом профиле; предыдущая копия и
мир сохраняются. Cache в этот объём не входит. Backup/restore пока синхронны:
обработка больших архивов может временно задерживать интерфейс.

## Ручная приёмка нового кандидата

19.11.2026 владелец подтвердил все новые сценарии A–F, включая focus и DPI, для
`LODANDSY-Iteration-2026-11-19.zip`. Запуск этого ZIP без установленного Python
пока не проверен; ARU-64 остаётся открытой. Точный SHA256 и ответ владельца — в
[записи приёмки](../docs/validation/2026-11-19-owner-acceptance.md).
Запись добавлена после передачи ZIP; проверенный архив не изменялся.

Ручной W2 preflight18.11 уже принят владельцем, библиотеки Qt/ADS не обновлялись.
Подтверждение прежнего MVP с Python не переносится на новые функции этой итерации.
Проверить новый кандидат:

- На Windows без установленного Python: запуск и создание/открытие проекта (ARU-64).
- Дерево/скрытый поиск/plus dropdown/child context/клавиши; два независимых редактора.
- Toolbar/Undo/source-preview-split, image file/paste/drop/alt/resize, пять templates.
- Большая карта, progress/cancel, несколько карт, pan/zoom, старые M1 pins/ссылки.
- Два image tokens на одну Card, properties/replace/delete/Undo, missing image/broken
  Card, grid offset/size/opacity/visibility/snap; выбор/zoom/grid не меняют координаты.
- Save→restart, backup→restore, старый S3 проект, layout/float/focus, mixed DPI/мониторы.

Автоматический frozen smoke/pytest-qt не является этой ручной приёмкой. Автоматический
smoke работает только во временном мире и не изменяет пользовательские данные:

```powershell
.\LODANDSY.exe --self-test --report "$env:TEMP\lodandsy-smoke.json"
```

Опционально --large-map-image "C:\Maps\large.jpg": полный smoke с указанным большим
фоном (Card/token используют отдельную маленькую картинку). Генерация cache может
занять время; отчёт явно указывает, выполнялась ли эта часть.

## Пересборка из source

Windows x64/CPython3.14.8; Qt/PySide6 6.11.2 + ADS5.1.1, pyvips3.2.0/binary8.18.7.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.lock
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pip check
```

Скопируйте LICENSES/LGPL-3.0-only.txt и GPL-3.0-only.txt из поставки в
.prototype-deps/license-texts/ source. Они взяты из официального Qt6.11.2 LICENSES.
libvips notices/versions/provenance лежат в build_support/licenses/. При обновлении
native DLL повторить prepare_vips_notices.py с указанными официальными архивами;
packager откажется собирать bundle при несовпадении SHA. Лицензии и source/build URLs —
THIRD-PARTY.md. Затем build_support/build_windows.ps1 -Archive NEW-NAME.zip.
Пересборка ничего не публикует. ICU78 исключена: Qt использует ICU Windows.
