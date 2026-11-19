# LODANDSY — действующий контракт, итерация 6-rev3

Утверждённый [пакет A–E](iterations/2026-11-19-iteration-6-rev3/CODEX-ITERATION-6.md)
заменяет противоречащие прежние решения. План и статусы — существующие Linear задачи;
фактические результаты — [отчёт6](validation/2026-11-19-iteration-6.md),
[архитектура](architecture/LODANDSY.drawio), приёмка — build_support/README.md.
Макеты6 с частным портретом не входят в public repo/поставку.

## Общий канон и границы (A, ARU-84/34–39/65)

Windows-first Python3.14/PySide6 6.11.2/Qt Widgets/ADS5.1.1; модульный монолит,
домен без Qt/SQL/UI. SQLite S3 через sqlite3, assets отдельно с относительными путями.
Текущий единственный формат SQLite13/Card4/Map5/Table3, UI state4. Legacy, миграции и
архивы старых тестовых форматов не обязательны; неподдерживаемый проект отклоняется
без записи. Реальные пользовательские папки автоматически не удаляются.

Core Entity: UUID/kind/title/parent_id/position + module payload. Единое смешанное дерево
Card/Map/Table, parent/cycles/order/duplicates валидируются; links отдельно от hierarchy.
EntitySession владеет выбором/transaction/generation; CardsService, TablesService,
MapsService — своими командами/данными/drafts. CardsController, TablesController,
MapsController, DiceController — своими views/session state/workers. AppController
собирает явные зависимости/navigation; ProjectActions выполняет составные операции без
widgets. Старые ApplicationSession/ModuleSession/ModuleController/card_images удалены.
Cards получает embedded Table factory; Maps получает публичные Card queries/actions,
не Card Editor; Dice не требует Entity/project/SQL. Нет locator/EventBus/ORM/второго store.

Одна EntityCollection и один SQLite writer. Post-commit адресные events ID+fields;
Card+Token, child inventory и cascade дают одно revision notification после атомарного
применения. Закрытие/смена проекта отменяют workers и инвалидируют generation. UI не
владеет отдельными копиями мира. AST-границы/отсутствие циклов проверяются автоматически.

Tree/Inspector фиксированы, native resize/collapse/rails сохраняются; ADS размещает,
WindowManager управляет жизнью независимых окон. Tree selection, active window, document
UUID и UI preferences раздельны. «+» раскрывает создание, поиск под кнопкой/Ctrl+F,
дочерние через контекст. Enter/двойной щелчок открывает/фокусирует существующее окно UUID.

## Таблицы, инвентарь и ввод (B, ARU-83/78/80/46)

Table — универсальная Entity с UUID rows/columns и immutable scalar cells. Типы text,
number, bool, entity_ref и projection. Column имеет стабильный key, constraints kind/
card_type, source_column_id+field_key для проекции, number integer/min/max/required/default.
Произвольных формул, отдельного Inventory store или игровых правил нет.

Инвентарь создаётся явно ровно один раз как настоящая дочерняя Table:

| Ключ | Колонка | Поведение |
|---|---|---|
| item | Предмет | nullable UUID любого Card(item) текущего мира |
| quantity | Количество | положительное целое, default1 |
| description | Описание | read-only summary либо краткий безопасный plain description |
| cost | Стоимость | read-only текущая единичная cost; None→«—»,0→0 |

Проекции не сохраняются в rows/SQLite. Замена item сохраняет количество; одинаковый
item в нескольких строках допустим. Rename/body/cost/type/delete адресно обновляют
зависящие строки через reverse index, без N+1 чтения storage при paint. Недоступный item
оставляет UUID+quantity и диагностику/повторный выбор; каскад инвентаря не происходит.
Удалённый source column сохраняет диагностируемую projection definition.

Native model/view picker ищет title/aliases, показывает path/UUID, Enter выбирает,
Escape отменяет;10k записей не создают10k widgets. Произвольный ввод/TSV UUID валидируется,
имена не превращаются в выдуманные UUID. Copy содержит UUID ref и displayed projections;
TSV paste только writable range, пересечение read-only range отклоняется целиком.
Header [+] не является model cell; context/drag меняют UUID-порядок без потери данных.

Structured input хранит локальный UUID buffer/baseline/raw text до Enter/Tab/blur,
Escape отменяет, checkbox/picker дискретны. Canon ACK не вызывает повторный setText или
reset активного editor; курсор/выделение/native Undo сохраняются в двух представлениях.
Конфликт не перезаписывает чужой канон. Удалённая ячейка сохраняет session orphan draft,
который можно прочитать/скопировать и явно отбросить. Ctrl+S/close/switch flush валидный
ввод; autosave других данных не публикует незавершённое слово.

## Card, интерфейс и media (C/D, ARU-26/75/76/33)

Card type-only, без templates/tags/aliases UI; смена типа сохраняет введённые значения и
разделы. Характеристики только Inspector; add-field не сбрасывает существующее значение.
Aliases остаются в данных/поиске/импорте. Один canonical title и явный Portrait contract.
CardSection UUID/title/position/kind rich_text|table_ref. Описание — единственная
purpose=description projection Card.content. До64 разделов,2MiB HTML/раздел,4MiB rich/Card.
Текст — контролируемый Qt HTML и непрерывный QTextDocument, coalescing250ms idle/max2s,
явный flush на save/switch/close. Нет reset/потери Undo/зависимости autosave от фокуса.

Native graphite #191919/#202020, hover#292929/selection#303030/divider#333333,
text#e5e5e3/muted#a6a6a3/accent#c9c7bf, primary#dededb; navy/blue-gold отменён.
Segoe UI, title32/body15 logical px; rail46/tree224/Inspector244 по умолчанию регулируются.
Card: breadcrumb/copy link, квадратный портрет слева, type/title/summary справа,
без отдельного scroll шапки. Обычно184px, narrow132, при сильном сжатии compact88.
Summary полностью редактируется через диалог. Prose≤760px, Table использует ширину окна.
Пустой портрет clickable; hover/focus replace/crop/remove overlay, без caption/description.

Paint использует актуальный contentRect, не iconSize от прошлого layout. Crop в oriented
source coordinates, square frame; no-change10циклов идемпотентны, прямоугольный saved rect
aspect-fit до явного recrop. Card/token используют один crop, token image override — свой
полный источник. Assets неизменяемы. При удалении раздела освобождаются только его
QTextDocument/preferences/embedded view/pending callbacks; Undo живых разделов сохранён.

Только lodandsy://entity/UUID через application navigation. Copy link — HTML fragment и
plain URI. HTTP(S) открывается только при явной активации; network resources не грузятся.
Остальные URI запрещены, local images только assets с traversal/symlink/junction защитой.
Media≤64MiB/32MP, EXIF-aware thumbnail≤1024, working set≤8MiB/document, sharedLRU16MiB,
до32 pending jobs. Недоступные/повреждённые media имеют понятную заглушку. Alt inline image
не является подписью портрета. Rich source при просмотре не переписывается.

## Map и Dice (C/D, ARU-77/81/79/70)

Viewer map:UUID и Editor map-editor:UUID независимы по lifecycle/camera/selection,
используют один MapService/Undo/writer/tiles. Viewer — token/grid/fit/pan/zoom/editor;
Editor — vertical tool rail/canvas/right layers/Object Card library/properties. Undo/Redo
IconOnly с command tooltip/scoped hotkeys, Space временно pan, Escape отменяет drag.

Библиотека только Card(object) с доступным main image, title/aliases search, thumbnail и
UUID. Import создаёт/выбирает Object Card. Размещение использует original image/alpha/
oriented aspect, long edge128 world px, без portrait crop; фиксирует asset+geometry,
будущая правка/удаление Card не меняет raster. Слои front сверху, up повышает list/scene z,
крайние действия выключены, выбор сохраняется по UUID. Layer visibility/rename/delete,
object x/y/width/height/rotation/z/move/delete/Undo сохранены. Нет прежней all-assets palette.

TokenInstance —0..N размещений Card с label/image/kind/footprint overrides. Card deletion
атомарно удаляет placements, Undo не воскрешает удалённую Card. Для inventory ref другая
политика — soft broken link. Background<raster layers<grid<tokens. Свободные центры,
footprint в клетках, snap нет; grid clipping/world transform/cosmetic pen сохраняются.

Большие изображения — прежний libvips worker/атомарная перестраиваемая пирамида ADR-011:
source≤2GiB,cache≤4GiB/32768tiles,worker≤512MiB/900s,tileLRU64MiB,BMP/GIF≤16MP,
SHA/version/source checksum, cancel/ошибки/перезапуск. Лимиты не повышены.

Tools/Dice — singleton tool:dice вне Entity, работает без мира: d4…d100/count/modifier,
формула, каждый результат и сумма, repeat/clear/copy/history≤50 в сессии. Сетка7+modifier,
result и история ограниченной ширины. Roll не dirty проект; switch не создаёт дубль.
Нет eval/presets/Dice Entity/random table mode/дополнительных игровых моделей.

## Надёжность и поставка (E, ARU-63/64/66)

Autosave/Ctrl+S используют один SaveCoordinator/revision writer, FK на каждом соединении.
Pending input, dirty/saving/saved, invalid draft и I/O error отображаются раздельно.
Валидный канон сохраняется при иных invalid drafts, ACK только после принятого изменения.
Close/switch: исправить/отбросить ошибочный ввод/отменить; данные не отбрасываются молча.
Backup/restore — канон+assets/checksum/inventory, без derived projection values и tiles.
Полный snapshot writer и synchronous backup≤4GiB сохранены: incremental changed-entity SQL
и bounded backup worker/progress/cancel — отдельные следующие работы, ARU-54 открыта,
ARU-45 Done относится к исходному snapshot/revision contract.

MOW read-only v1 subset сохраняется: preview/report→skip/remap→atomic apply, source UUID/
type/aliases/summary/safe fields/media/links; исключённые tags/templates/unsafe/runtime
controls отражаются в отчёте. Импорт не превращает prose в придуманный инвентарь.

Targeted batches после A–D, полный итоговый gate после стабилизации; Windows frozen smoke,
native libraries/licenses/source parity, ZIP CRC/manifest/SHA, architecture draw.io и
единый чек-лист6 требований+2дефектов+последнего дополнения. Qt render не заменяет native
capture/ручную визуальную приёмку. MixedDPI/второй монитор и чистая Windows без Python
учитываются отдельно. Done не выставляется без обязательной приёмки; public release нет.
