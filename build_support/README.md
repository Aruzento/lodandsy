# LODANDSY — Windows-кандидат итерации 5

Распакуйте всю папку LODANDSY на Windows10/11 x64, запустите LODANDSY.exe.
Python/Qt/ADS/libvips встроены в _internal; exe отдельно не переносится. Мир создавайте
отдельно: project.sqlite3 + assets — канон; .lodandsy-ui.json — UI; .lodandsy-cache —
перестраиваемые тайлы. Текущий формат SQLite12/Card4/Map5/Table2. Старые тестовые версии
отклоняются без записи; обязательных миграций нет. URI только lodandsy://entity/UUID.
Это новый кандидат, прежний W2 preflight не является его визуальной приёмкой.

## Ручная приёмка — 23 замечания

1. Создать Card через «+»: отсутствует выбор самостоятельного шаблона.
2. Создать базовые типы и сменить тип: введённые значения/разделы сохраняются.
3. «+» вкладок: текст → rename через ПКМ → edit/Undo → close/reopen, UUID стабилен.
4. HP/AC/скорость только Inspector,0/false/unset корректны; повтор «Добавить поле» не
   сбрасывает HP15, в выборе только допустимые отсутствующие поля.
5. В Card нет aliases/tags, tags нет в поиске/модели. Aliases импорта сохранены как данные.
6. Hero: название/тип/краткое описание/портрет/вкладки; нет длинной панели служебных форм.
7. Инвентарь создаёт одну дочернюю Table; правки/invalid draft общие с самостоятельным
   окном. Rename вкладки/таблицы не меняет UUID. Удалить вкладку — Table остаётся;
   move/delete Table даёт диагностику ссылки и явную замену, без дубля.
8. Портрет заметный на широком окне, не поглощает узкий dock при плавном resize.
9. Пустая область портрета сама открывает выбор картинки мышью/клавиатурой.
10. У загруженного портрета replace/crop/remove видны при hover/focus, доступны с Tab,
    имеют tooltip; снятие не удаляет общий asset.
11. Crop: рамка/dim/drag/zoom/preview/Apply/Cancel/Reset; EXIF фото и размеры/DPI. Cancel
    оставляет crop, Apply сохраняется после restart/backup. Все наследующие токены обновлены,
    image override не получает чужой crop. Источник не изменён, копий assets не появляется.
12. Нет полей/диалога подписи/описания портрета и кнопки «…» рядом с ним.
13. Сетка: маленькая прямоугольная карта по центру большого viewport; fit/pan/resize/
    fractional zoom/100–125–150%/перенос между мониторами. Grid совпадает с bounds и
    offset фона, линии тонкие/без тени, drag не оставляет следов.
14. Нет snap в UI; токены движутся свободно, footprint в клетках не меняется от zoom.
15. Viewer: нет отдельной кнопки переименования карты, имя через Tree/Inspector.
16. «Редактировать карту» открывает отдельное окно: tools/layers/assets слева, canvas,
    inline transforms справа. Import/existing asset/place/move/resize/rotate/z/delete,
    layer name/order/visibility/deleteconfirm. Escape отменяет drag, Space — pan.
    Viewer и editor вместе: данные/Undo общие, камеры разные, закрываются независимо,
    повторное открытие фокусирует окно; delete Map закрывает оба.
17. Undo/Redo одинаковые curved arrows с tooltip; Ctrl+Z/Y меняют только активный редактор,
    не скрытый rich-раздел/соседнюю Table/другую карту.
18. Table универсальна, нет random chooser/result panel/кнопок создания копий документа.
19. [+] после последнего заголовка столбца и номера строки; пустая Table работает. Плюсы
    не попадают в TSV/SQLite/содержимое, доступны после прокрутки в конец.
20. ПКМ заголовка: name/type/delete с подтверждением данных; drag заголовка меняет порядок
    без потери UUID/значений/выделения; type отказ не уничтожает ячейки.
21. «Инструменты → Кубики» рядом с «Проект», доступно без мира, один tool:dice. Нет Dice
    в Tree/Create и preset CRUD; roll не dirty мир, layout не создаёт дубль, project switch
    оставляет тот же инструмент.
22. Кубики сеткой на узком/широком dock: d4…d100/modifier/formula/каждый результат/крупная
    сумма/repeat/clear/copy/history50; нулевой/чрезмерный бросок безопасен.
23. Tree/Inspector растягиваются native разделителями, скрытие/возврат и restart сохраняют
    ширины. Inspector без выбора показывает подсказку. Dock/center/insert/float/redock,
    maximize→drag, focus/Tab, два монитора/mixedDPI не конфликтуют с боковыми областями.

## Сквозные проверки

- Cards A/B + viewer/editor + Table + tool:dice одновременно;20 inline images, scroll туда/
  обратно, несколько окон/crop/close/reopen, bounded caches, missing/corrupt placeholder.
- Invalid Card/number Table draft + валидная правка другой Card → Ctrl+S/autosave:
  валидное сохранено, draft явно помечен; I/O error отличается. Close/switch: Исправить /
  Отбросить ошибочный ввод / Отмена, без потери уже сохранённых данных.
- Суммарный rich budget4MiB по нескольким UUID-вкладкам: отказ видим, исходный канон не
  подтверждён преждевременно, Undo/смена вкладки/close/reopen корректны.
- MOW реальный sample и каталог: preview/report, skip/remap; aliases/source metadata/links/
  supported assets перенесены, tags/template/portrait caption исключены с отчётом, старый
  текст не создаёт выдуманный инвентарь. Источник не меняется, network/JS не исполняются.
- Save→restart сохраняет UUID/sections/crop/child Table/layers/objects/placements/layout.
  Backup вне мира → restore в новую папку: данные/ресурсы совпадают, тайлы перестраиваются.
- Большая карта PNG/JPEG/WebP, два окна/1000tokens, cancel/error/rebuild cache. Не объявлять
  массу объектов SLA. Именно новый ZIP запустить на чистой Windows без Python и в
  кириллическом пути. ARU-64 пока не закрывать запуском на машине с Python.

## Воспроизведение и ограничения

```powershell
.\LODANDSY.exe --self-test --report "$env:TEMP\lodandsy-smoke.json"
# опционально: --large-map-image "C:\Maps\large.jpg"
```

Это автоматический smoke во временном мире, не ручная визуальная приёмка.
Build из source: CPython3.14.8 x64 + requirements-build.lock,
`build_support/build_windows.ps1 -Python .venv/Scripts/python.exe -Archive LODANDSY-Iteration5-2026-11-19.zip`.
source/MANIFEST.sha256 и docs/validation/iteration5-frozen-source.json фиксируют
исходники и проверку compiled code; внешний SHA — соседний .zip.sha256. LICENSES и THIRD-PARTY.md в дистрибутиве.

Backup/restore пока синхронны,≤4GiB без tile cache; full snapshot writer остаётся.
Background backup/progress/cancel/incremental SQL — отдельные задачи. Source map≤2GiB,
cache≤4GiB/32768tiles, worker512MiB/900s, tileLRU64MiB, BMP/GIF≤16MP. Media64MiB/32MP,
thumbnail≤1024, documentLRU8MiB/shared16MiB/32pending. MOW≤500файлов/2MiB/64MiB total,
v1 subset. Эти пределы не являются SLA; реальные измерения и непроверенные пункты — отчёт.
