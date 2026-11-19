# LODANDSY — текущий контракт, итерация 4

Локальная нативная рабочая среда ведущего: несколько Cards, карты, таблицы и кубики
сосуществуют и надёжно сохраняются. План и статусы — существующие задачи Linear.
Утверждённый пакет: iterations/2026-11-19-iteration-4/CODEX-ITERATION-4.md.
Реализация/измерения: validation/2026-11-19-iteration-4.md. ADR-019…022 уточняют контракт.

## Общие инварианты

Python3.14 / PySide6 Qt Widgets / Qt ADS5.1.1 / SQLite S3 через sqlite3, без ORM.
Модульный монолит domain/application/ui; домен без Qt и SQL. Entity — минимальный
id/kind/title/parent_id/position + payload модуля. Один смешанный лес Card/Map/Table/Dice,
без групп типов, с проверкой родителя/циклов/порядка/UUID. Ссылки не являются иерархией.
Tree/Inspector/rails фиксированы; ADS размещает, WindowManager управляет жизнью окон.
Выбор дерева, открытый документ, активное окно и UI state независимы. Один редактор ID.
Создание — плюс с меню, поиск под кнопкой/Ctrl+F, дочерние — контекстное меню.

SQLite schema11: Cardv3/Mapv4/Tablev2/Dicev2. UUID стабильны, assets отдельно, пути
относительные; FK включены на каждом соединении, составные операции транзакционны.
Autosave и Ctrl+S — один упорядоченный writer с dirty/saving/error и видимыми отказами.
По общему решению владельца legacy форматы/Markdown/адаптеры/режимы не сохраняются без
доказанной необходимости; обязательные миграции и архивирование тестовых миров отменены.
Неизвестные schema/payload/kind отклоняются без записи. Существующие файлы не удаляются.
Ни параллельного S1, ни автоматической конвертации старой SQLite в текущую нет.

## A — каноническая карточка (ARU-80/65)

Entity.kind=card, CardTypeDefinition определяет смысл; TemplateDefinition — компоновку
SectionDefinition. Независимая смена типа/шаблона сохраняет поля и текст. FieldDefinition
задаёт стабильный ключ, тип, default/unset, группу, ограничения; custom schema builder нет.
Title только Entity.title (name — проекция). Description — единственный основной Qt HTML;
notes/history/connections/inventory — отдельные rich области. Summary/tags/aliases,
race/class_or_role/hp/ac/speed, rarity/weight/cost, region/climate/danger_level — typed
values; 0/false/None/отсутствие различаются. Нет извлечения характеристик из HTML.
Изменения атомарно валидируются ApplicationSession, адресные события содержат ID/ключи.
Card UI/Inspector/search читают один канон; невалидный ввод — видимый сессионный draft,
блокирует save, переживает закрытие редактора и явно отменяется либо исправляется.

## B — визуальный редактор (ARU-26/75/76)

Native QTextEdit/QTextDocument с безопасным Qt HTML, без web runtime. Шапка: название,
тип/компоновка, summary, tags/aliases, встроенный портрет aspect fit; alt/caption/replace/
remove доступны контекстно. В узком окне портрет перемещается над текстом. Compact toolbar
сохраняет шрифт/размер/цвет/B/I/U/strike/заголовки/списки/align/код/links/images/Undo.
Пять компоновок: Пустая/Статья/Персонаж/Локация/Предмет, без копий названия/статов в HTML.
Каждая rich область имеет свой QTextDocument/Undo/курсор/scroll/масштаб в сессии.
Единственный внутренний URI lodandsy://entity/UUID; opens/focus через application layer,
подпись независима, удалённая/некорректная цель диагностируется. Copy — URI + HTML fragment.
HTTP/HTTPS открываются только при явной активации; network resources/иные схемы запрещены.
Media только внутри assets текущего проекта; protected whitelist и бюджеты HTML.

## C/D — размещения Card и сетка (ARU-77)

TokenInstance всегда имеет card_id и собственный UUID; одна Card → 0..N размещений на
разных картах. Хранит координаты, footprint, z/optional layer и явные nullable label/image/
kind overrides. Title/portrait/token defaults/summary/HP читаются из Card через адресное
уведомление; overrides видны в свойствах/tooltip и сбрасываются. Нет копий игровых статов.
Card из Tree можно перетащить на карту без перемещения в иерархии; добавление выбирает
существующую либо создаёт новую Card. Double click opens/focus. Удаление размещения сохраняет
Card; удаление Card явно предупреждает числом размещений и атомарно удаляет их вместе с ней.
Undo карты не воскрешает удалённую Card/её размещения. Неожиданная broken reference сохраняет
диагностику, без автосоздания канона. Character — circle crop/white border, item — alpha/
aspect fit без постоянной рамки. Footprint1×1/2×2/3×3 и больше, не зависит от zoom.
Grid: world cell/offset/color/opacity/snap; смена настроек не двигает центры. Один тонкий
физический пиксель, LOD только viewport линий, без старой3px тени. Full viewport repaint
исключает накопление alpha при drag. Мир/snap не меняются от LOD/DPR.

## E — слои и декор (ARU-81)

MapLayer UUID/title/position/visible; PlacedAssetObject UUID/layer/asset/x/y/width/height/
rotation/z, kind=raster. Объект не является Token/Card. Background tiles, layers/objects,
TokenInstance, grid и view state разделены. «Редактировать карту» включает выбор/создание/
переименование/порядок/видимость слоя, import/existing asset, place/move/properties resize/
rotation/delete/Undo. В обычном режиме работают токены; режимы не перехватывают чужой drag.
Hidden сохраняет данные; непустой слой удаляется только с явным подтверждением содержимого.
Background < raster layers < grid < tokens. Общие assets/cache, missing placeholder.
До1000 слоёв/10000 объектов/10000 размещений на карту — валидационные пределы, не SLA.
Новых path/wall/light/physics/процедурных/боевых моделей нет.

## F — импорт MOW (ARU-82)

Однонаправленный импорт файла/каталога: preview/report → skip/remap → prepare → atomic apply,
в выбранный узел текущего/нового проекта. Источник только читается. MOW v1 YAML header с
плоскими scalar/inline lists и HTML card-shell/entity-main; опасные/вложенные YAML конструкции
отклоняются, без новой зависимости. Два прохода новых UUID/parent/order/wiki-links, повторные
source UUID не перезаписываются. Missing parent явно становится корнем/выбранным местом,
duplicate/cycle/corrupt — отказ всего apply. Source UUID/type хранятся как typed metadata.
Title/type/tags/aliases/summary/body/поддержанные media переносятся, runtime controls/JS/CSS
не исполняются и исключаются. Generic local img src только внутри source root через общий
assets importer; symlink/junction/traversal/network запрещены. .wiki-link[data-page-id]
переводится в entity/UUID; неразрешённые ссылки/unknown blocks диагностируются. MOW data-asset
без manifest не угадывается. Реальный предоставленный sample и synthetic fixtures проверены
раздельно; полной совместимости со всеми MOW разновидностями/structured v2 не заявляется.
Бюджеты:500 файлов,2MiB/файл,64MiB суммарно,200000 HTML узлов на import,64 уровня/20000
узлов на документ. Ошибка не публикует часть карточек, новые unreferenced staged assets очищаются.

## Tools, сохранение и G

Typed Table: UUID колонок/строк, text/number/bool, atomic TSV, invalid drafts, copy диапазона,
случайная целая непустая строка;0/false — данные. Изменённая ячейка уведомляет адресно;
неизменные immutable rows переиспользуют proof cache валидации типа. Схема меняется с полной
проверкой. Snapshot writer остаётся полным; incremental SQL/lazy loading — отдельное развитие.
Dice: d4/d6/d8/d10/d12/d20/d100, модификатор, каждый результат/сумма, именованные UUID пресеты,
повтор/copy; RNG инъецируется, eval нет, roll не dirty, сессионная история≤50.
Rich images: visible draw working set,8MiB/document,16MiB shared LRU,32 queued jobs,
thumbnail≤1024, metadata layout без декодирования всех изображений. Evict/reload на scroll;
closed section state не держит bitmap, Undo/source не меняются. Pending ≠ unavailable.
Raster media≤64MiB/32MP. Большие карты — libvips ADR-011: source2GiB, cache4GiB/32768tiles,
worker512MiB/900s, GUI tileLRU64MiB; BMP/GIF≤16MP. SHA/version/atomic pyramid publication,
progress/cancel/rebuild; никакого полного background QPixmap в GUI.
Backup/restore≤4GiB суммарно, включая все assets, без производных tiles. Checksum/integrity/
FK/no-overwrite restore; ошибка не заменяет предыдущий backup. Пока синхронны, ARU-54 открыта
для фонового bounded snapshot/copy, progress/cancel/disk-space preflight. Объём не увеличен.

A–F — целевые проверки на границах; G — один полный pytest/Ruff/pip/diff gate, Windows frozen
build/smoke/source parity/ZIP CRC/SHA/licenses. Ручные focus/dock/float/maximize→drag/мониторы/
mixed DPI и чистая Windows без Python обязательны отдельно; smoke не заменяет их.
ARU-63/64 остаются открыты до фактической приёмки нового кандидата. Один итоговый отчёт.
Commit/push/merge/release только после нового отдельного разрешения владельца.
