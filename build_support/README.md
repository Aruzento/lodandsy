# LODANDSY — Windows-кандидат итерации 3 (19.11.2026)

Распакуйте всю папку LODANDSY на Windows10/11 x64 и запустите LODANDSY.exe.
Python/Qt/libvips встроены в _internal. Exe отдельно не переносится. Мир создавайте
в отдельной папке; project.sqlite3 и assets/ — данные, .lodandsy-ui.json — интерфейс,
.lodandsy-cache — перестраиваемые тайлы. Публичного release нет.

Только текущая SQLite schema10, Cardv2/Mapv3/Tablev2/Dicev2. По решению владельца
legacy Markdown/старые форматы/миграции/архивирование отменены. Старый проект ожидаемо
отклоняется без записи; создайте новый тестовый мир. Единственная ссылка entity/UUID.
Сборка прошлой итерации и её приёмка не покрывают этот кандидат.

## Чек-лист десяти замечаний

1. Визуальный Card: написать текст, выделить фрагмент, изменить шрифт/размер/цвет,
   B/I/U/strike/выравнивание/списки/код. Undo/Redo, close/reopen, курсор/прокрутка/масштаб.
   Открыть две Cards: ввод/Undo в A не меняет B. Режимов source/preview/split нет.
2. Портрет в шаблоне «Персонаж»: выбрать/заменить/убрать, caption/alt, aspect fit.
   Inline-картинка остаётся независимой. Удаление портрета не удаляет общий asset.
   Проверить placeholder на копии мира с временно недоступным изображением.
3. Единое дерево без разделов: создать Card/Map/Table/Dice, вложить любые типы,
   mixed drag/reorder/root drop, отклонить цикл. Плюс с меню, поиск под кнопкой,
   дочерние через context; Inspector/selection и открытые документы независимы.
   Копировать ссылку/вставить в Card, Ctrl+click открывает или фокусирует цель.
4. Сетка видна у новой карты: настроить show/cell/offset/color/opacity/snap,
   проверить светлый/тёмный фон и дальний zoom. На дальнем zoom линии укрупняются,
   но шаг snap остаётся исходным. Смена настроек сама не перемещает токены.
5. Есть один Token: toolbar/ПКМ, создать с картинкой либо placeholder. Название,
   связь с любым документом, новая Card/open/unlink/delete, Undo/Redo. MapPin нет.
   Удалить связанную Card: токен сохраняется с разорванной ссылкой.
6. Character круглый: изображение обрезано по кругу, белая рамка; выбор/drag/zoom,
   тёмный и светлый фон, фото разных пропорций, missing image.
7. Размер по клетке: default1×1, свойства2×2/2×3, изменение cell_size меняет footprint
   без движения центра. Snap учитывает верхний левый угол footprint, в том числе2×2.
   На краю центр ограничен исходником, часть footprint может выходить за изображение.
8. Item: исходные пропорции, alpha, без постоянной рамки; выделение видно.
   Замена картинки и переключение kind не меняют UUID/связь/координаты. Обе разновидности
   на нескольких больших картах; source/cancel/cache/reopen — libvips tiles.
9. Table: text/number/bool колонки; имя/порядок/добавление/удаление строк и колонок,
   отказ удаления с данными, строгий отказ несовместимой смены типа, tab/edit/checkbox.
   Ctrl+S во время ввода сохраняет валидную ячейку. Invalid draft подсвечен и блокирует
   save, переживает close/reopen в сессии; исправить либо «Отменить ввод».
   Copy диапазона, TSV paste целиком или отказ, случайная целая запись;0/false не пусты.
10. Dice: визуальные d4/d6/d8/d10/d12/d20/d100, счётчики/модификатор/смешанный бросок,
    каждый результат и сумма, повтор/очистка/copy. Заготовки создать/назвать/дублировать/
    выбрать/удалить. Zero/слишком много — понятная ошибка. Roll не dirty; history≤50 в сессии.

## Общая ручная приёмка

- Одновременно Cards A/B, Map, Table, Dice: dock во все стороны/center/insert/float/
  redock/maximize→drag без прыжка, клавиатурный focus и локальные Ctrl+Z/Ctrl+Y.
- Ctrl+S/autosave → закрыть приложение → открыть мир: данные/UUID/ссылки/портрет/
  токены/сетка/таблица/пресеты/layout/камера/выбор восстановлены. История бросков
  между запусками не сохраняется. Tree не переключает контекст открытого редактора.
- Backup вне мира → restore в новую папку → тот же результат; cache перестроится.
  Бюджет backup/restore4GiB без cache. Эти операции пока синхронны.
- PNG/JPEG/WebP большие карты, несколько окон, cancel/ошибка/повторное открытие.
  Source2GiB/cache4GiB/32768tiles/worker512MiB/900s/GUI LRU64MiB. BMP/GIF bounded16MP.
  Card/portrait/token raster≤64MiB/32MP. Сеть не загружается, assets не выходят из проекта.
- Два монитора с разным DPI, перенос/floating/restore/отключение монитора.
- Именно этот ZIP на Windows без установленного Python: запуск и весь цикл выше.
  Прежний W2 preflight принят; новая полная сборка без Python остаётся ARU-64.

Автоматический frozen smoke работает во временном мире и не заменяет ручную приёмку:

```powershell
.\LODANDSY.exe --self-test --report "$env:TEMP\lodandsy-smoke.json"
```

Для большого фона добавьте --large-map-image "C:\Maps\large.jpg".
Source manifest — source/MANIFEST.sha256. Контрольная сумма ZIP в соседнем .zip.sha256.

## Воспроизводимая пересборка

Windows x64/CPython3.14.8, PySide6/Qt6.11.2, ADS5.1.1, pyvips3.2.0/binary8.18.7.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.lock
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pip check
.\build_support\build_windows.ps1 -Archive LODANDSY-Iteration3-2026-11-19.zip
```

LICENSES/LGPL-3.0-only.txt и GPL-3.0-only.txt из прежней поставки/официальных Qt LICENSES
нужны в .prototype-deps/license-texts/. libvips notices/версии/provenance — build_support/
licenses, сборщик проверяет SHA native DLL. При обновлении повторить prepare_vips_notices.py.
THIRD-PARTY.md содержит лицензии/source/build URLs. ICU78 исключена: используется ICU Windows.
Сборка ничего не публикует; commit/push/merge требуют отдельного разрешения.
