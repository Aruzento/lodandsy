# LODANDSY — текущий контракт, итерация 5

Нативная локальная среда ведущего: независимые Card, Map, Table и инструмент кубиков.
Утверждённый пакет: [A–G](iterations/2026-11-19-iteration-5/CODEX-ITERATION-5.md).
План/статусы — существующие задачи Linear. Факты — [отчёт](validation/2026-11-19-iteration-5.md),
ручная приёмка — build_support/README.md. Новые требования отменяют противоречащие старые.

## Общий контракт

Python3.14 / PySide6 6.11.2 / Qt ADS5.1.1; модульный монолит domain/application/ui,
домен без Qt/SQL. SQLite S3 через sqlite3 — единственный канон, assets отдельно с
относительными путями. SQLite12 / Cardv4 / Mapv5 / Tablev2. Entity: UUID/kind/title/
parent_id/position + payload модуля. Смешанный лес Card/Map/Table, валидированные parent,
cycles и order, ссылки не являются иерархией. Неизвестная версия/повреждение отклоняются
без перезаписи. Обязательные миграции, legacy Markdown, прежние шаблоны/режимы/адаптеры
отменены владельцем; реальные папки не удаляются, тестовые разрешено пересоздавать.

Tree/Inspector — фиксированные боковые области с native draggable разделителями,
сохранением ширины/collapse; rails снаружи. ADS размещает, WindowManager управляет
жизнью окон. Выбор Tree, активное окно, документ и UI state раздельны. «+» с меню,
поиск под кнопкой/Ctrl+F, дочерние через контекст. Enter/двойной щелчок фокусирует окно
UUID. UI state v4: раскладка/камеры/ширины/активные UUID-вкладки/курсоры, отдельно от канона.

## A/B — Card и разделы (ARU-80/83/75/76/33)

Единственный выбор — card_type. CardTypeDefinition задаёт начальные разделы и применимые
поля; смена типа сохраняет введённые значения/разделы. Самостоятельного шаблона нет.
Entity.title один, summary в шапке. HP/AC/скорость и другие характеристики — только
Inspector через ApplicationSession. Неприменимые старые поля скрыты, данные сохранены.
«Добавить поле» предлагает допустимые отсутствующие; повтор отвергается доменом/сессией,
не сбрасывает значение. Aliases только в данных/импорте, tags удалены. Portrait — явный
media contract, не дублируется в values.

CardSection: UUID/title/position/kind rich_text|table_ref. Rich содержит контролируемый
Qt HTML; table_ref — UUID дочерней Table либо пустую явную заготовку. Описание одно;
Card.content — вычисляемая проекция purpose=description. «+» создаёт текст/дочернюю Table
либо связывает существующую дочернюю Table. Контекст: rename/order/delete с подтверждением.
Каждая rich-вкладка имеет свой QTextDocument/Undo/selection/scroll, сохраняемый при
rename/close/reopen. До64 разделов, до2MiB HTML/раздел и до4MiB суммарного rich-текста.

Персонаж/существо: Описание, История, Связи, Инвентарь, Заметки. Инвентарь создаётся
явной кнопкой ровно один раз атомарно: дочерняя Table «Предмет» text / «Количество» number /
«Описание» text. Встроенная Table и самостоятельное окно используют один ModuleSession
и общие invalid drafts. Удаление вкладки оставляет Table. Удалённая/перемещённая цель
показывает недоступную связь и явную замену, без создания дубликатов.

## C — интерфейс и media (ARU-26/76/75)

[Визуальный контракт](design/iteration-5-layout.md): navy/black, спокойный gold, единые
отступы/иконки, compact tools и keyboard/focus. Hero: название/тип/summary и портрет
до280 logical px на широком окне, на узком — вертикально. Пустой портрет clickable;
replace/crop/remove — hover/focus действия без подписи/описания/меню. Asset не изменяется
и не удаляется. Crop — нормализованный rect ориентированного изображения, рамка/dim/
drag/zoom/preview/Apply/Cancel/Reset. Bounded decoder учитывает EXIF. Наследующий токен
получает crop портрета, token image override не получает чужой crop. Undo/Redo — единые
изогнутые стрелки, tooltip, scoped Ctrl+Z/Ctrl+Y.

Только lodandsy://entity/UUID через application navigation. Copy link — HTML fragment и
plain URI. HTTP/HTTPS только по явной активации, preview не загружает network. file/
javascript/прочие схемы запрещены. Local images только внутри assets с защитой traversal/
symlink/junction и HTML whitelist. Rich media≤64MiB/32MP, thumbnail≤1024; visible working
set≤8MiB/document, shared LRU16MiB, до32 pending jobs. Закрытый раздел не удерживает bitmap,
scroll возвращает вытесненные изображения, Undo/source не меняются. Alt inline image
не является caption портрета.

## D — карты (ARU-77/81/70/63)

Viewer map:UUID и отдельный Map Editor map-editor:UUID — два ADS-окна одной Map, общий
ModuleSession/Undo/writer/tiles, разные камеры/selection. Повторное открытие фокусирует
окно, закрытие одного сохраняет другое, удаление Map закрывает оба. Viewer — токены/
pan/zoom/grid/fit. Editor — select/pan/place, слои/палитра слева, canvas, inline x/y/width/
height/rotation/z справа; import/place/move/delete/Undo. Escape отменяет текущий drag,
Space временно включает pan. Старый встроенный edit-mode удалён.

MapLayer и PlacedAssetObject raster независимы от Card/Token: UUID, общий asset, visible/
order/rotation/z; удаление непустого слоя подтверждается. Background < raster layers <
grid < tokens. TokenInstance — размещение существующей Card с явными label/image/kind/
footprint overrides. Одна Card в нескольких точках/картах; удаление Card предупреждает
числом размещений и атомарно удаляет их; Undo не воскрешает удалённую Card. Неожиданная
broken reference диагностируется. Character круг/white border, item aspect/alpha без
рамки. Footprint в клетках, свободные центры. Snap удалён. Grid рисуется/клипуется в world
coords одним transform, cosmetic pen без resetTransform/двойного offset. LOD только линий.

Большие PNG/JPEG/WebP — существующий libvips worker/атомарная пирамида ADR-011. Source≤2GiB,
cache≤4GiB/32768tiles, worker≤512MiB/900s, GUI tile LRU64MiB, BMP/GIF≤16MP. SHA/version/
cancel/error/rebuild, нет частичной публикации/полного background QPixmap в GUI. Decor
только bounded media. До1000 слоёв/10000 объектов/10000 токенов — валидационные пределы,
не SLA. Fog/combat/light/vector physics вне контракта.

## E/F — Table и Dice (ARU-78/79)

Table — универсальный документ UUID строк/колонок, text/number/bool;0/false — данные.
Компактные [+] после последнего заголовка столбца и номера строки — контролы, не ячейки.
Пустая Table работает. Контекст: name/type/delete с подтверждением непустых данных;
header drag меняет канонический порядок. Atomic TSV/copy диапазона. Нет random chooser/
result panel/toolbar перемещения и дублирования. Адресные dataChanged; immutable row
proof cache для правок, полная проверка схемы. Инвентарь использует тот же TableWidget.

«Инструменты → Кубики» доступно без проекта. Одно окно tool:dice, не Entity, без SQL/
payload/preset CRUD. d4/d6/d8/d10/d12/d20/d100, адаптивная сетка2–4 колонки, счётчики,
модификатор/формула/каждый результат/общий итог, repeat/clear/copy, история≤50 в сессии.
Смена/закрытие проекта не создаёт дубль и не dirty канон. Eval нет, RNG тестируемый,
невалидный/нулевой бросок безопасен.

## G — сохранение, импорт и поставка

Autosave/Ctrl+S — один SaveCoordinator, упорядоченные ревизии dirty/saving/error, FK на
каждом соединении, составные операции транзакционны. Invalid Card/Table ввод остаётся
явным session draft, канон хранит последнее допустимое значение. Draft не блокирует
сохранение валидных данных; статус отдельно сообщает несохранённый ошибочный ввод.
Перед закрытием/сменой: Исправить / Отбросить ошибочный ввод / Отмена. Валидные изменения
сохраняются до отбрасывания draft; I/O error отделён от draft/dirty. Rich content получает
application ACK прежде canonical_content; отказ бюджета видим, draft/Undo сохраняются.

MOW — read-only однонаправленный v1 YAML subset + HTML preview/report → skip/remap →
atomic apply, не legacy runtime. Source UUID/type/aliases/summary/safe fields/media/links
сохраняются; tags/template/portrait caption-description исключаются с отчётом. Текст не
превращается в выдуманный инвентарь. Два прохода UUID/parents/order/links; cycles/duplicates/
unsafe YAML/network/JS/runtime controls запрещены. Local img только в source root,
data-asset без manifest диагностируется. До500файлов/2MiB каждый/64MiB суммарно,200000
HTML узлов/import,64уровня/20000узлов rich document. Ошибка очищает лишь собственные
неопубликованные staged assets; источник не меняется.

Backup/restore: канон+assets, inventory/checksum, без tiles; лимит4GiB и синхронная GUI
операция сохраняются. Full snapshot writer, incremental SQL/lazy load, background backup/
progress/cancel — отдельные работы ARU-45/46/47/52/54 (ADR-022/026), не решённые редизайном.

После стабилизации полный pytest/Ruff/pip/diff, frozen smoke/native libraries/licenses/
source parity, ZIP CRC/SHA и ручной чек-лист23 пунктов. Qt render не заменяет native
визуальную приёмку. Clean Windows без Python, physical mixedDPI и новый внешний вид
требуют отдельного подтверждения владельца (ARU-63/64/66).
