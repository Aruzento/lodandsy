# LODANDSY — Windows-кандидат итерации 6-rev3

Распакуйте всю папку LODANDSY на Windows10/11 x64, запустите LODANDSY.exe.
Python/Qt/ADS/libvips встроены в _internal; exe отдельно не переносится. Мир создавайте
отдельно: project.sqlite3 + assets — канон; .lodandsy-ui.json — UI; .lodandsy-cache —
перестраиваемые тайлы. Текущий формат SQLite13/Card4/Map5/Table3. Старые тестовые версии
отклоняются без записи; обязательных миграций нет. URI только lodandsy://entity/UUID.
Это новый кандидат, прежний W2 preflight не является его визуальной приёмкой.

## Ручная приёмка итерации6-rev3

Проверять именно новый ZIP, в отдельном тестовом мире. Предыдущие W2/итерации не
заменяют эти сценарии. Отметки ниже оставлены открытыми до фактической ручной приёмки.

| № | Сценарий и ожидаемый результат | Статус |
|---|---|---|
|1|Модули: Card/Table/Map Viewer/Map Editor/Dice открываются независимо; закрытие соседних окон не выключает операции. Одна Table одновременно встроена и открыта отдельно.|□|
|2|Инвентарь: Предмет/Количество/Описание/Стоимость; picker ищет title/aliases, различает одинаковые имена по path/UUID, Enter/Escape. Только item, количество default1/целое>0; replacement сохраняет число, дубли item допустимы.|□|
|3|Item rename/summary/body/cost/type/delete обновляют только связанные строки обоих представлений. Cost0 отличается от unset«—»; недоступный item сохраняет UUID+quantity и позволяет повторный выбор. Description/cost read-only; TSV с projection/невалидным UUID отвергается целиком.|□|
|4|Нейтральный graphite Shell/ADS/popups/таблицы/focus: rail/Tree/workspace/Inspector, регулируемые разделители. Card — портрет слева, type/title/summary справа, breadcrumb/copy link, вкладки/+ одной строкой, без scrollbar шапки; prose читаемой ширины, Table full width.|□|
|5|Две Card с разными landscape/portrait изображениями: resize, switch10раз, close/reopen/load callback не меняют квадратную геометрию. Пустой портрет clickable; hover/Tab доступны replace/crop/remove. Полный summary открывается в диалоге.|□|
|6|Crop:10 последовательных открытий/Apply без изменения не меняют область/масштаб; Cancel неизменен. Drag/zoom/reset работают на разноцветных landscape/portrait/square/EXIF. Card/token используют выбранную область, override отдельно, source bytes не меняются. Undo/Redo карты только стрелки с command tooltip, Ctrl+Z действует в активном контексте.|□|
|7|Аудит:100 циклов create/open/delete rich/table вкладок, несколько Card окон, pending image, удаление/перемещение/повторная привязка Table. Нет накопления удалённых views/docs/предпочтений; Undo живых разделов сохранён.|□|
|8|Аудит: explicit/custom/empty sections создаются без конфликта default content; обычное создание по типу работает. Повтор add-field не сбрасывает HP15, отсутствуют legacy adapters/режимы.|□|
|9|Встроенная+standalone Table: настоящее непрерывное typing, кириллица, пауза>750ms, вставка в середину, selection/backspace/native Undo. Focus/caret/текст не прыгают при обновлении соседней строки/item/Inspector. Enter/Tab/blur подтверждают целиком, Escape отменяет.|□|
|10|Card title/summary и Inspector numeric: ввод без публикации каждой буквы, invalid draft отмечен. Ctrl+S прямо из активного поля сохраняет валидный ввод, сохраняет focus/selection/Undo; autosave другой Card не завершает чужое слово.|□|
|11|Два представления меняют одну ячейку: конфликт показан, raw не перезаписывает чужой канон. Row/column reorder сохраняет редактор UUID; удаление во время ввода оставляет доступный для copy orphan draft. Закрытие/смена проекта предлагают исправить/отбросить/отменить; I/O error/retry отличаются от draft.|□|
|12|Map Editor библиотека: только Card(object) с доступным main image, title/thumbnail/search/UUID; чужие portrait/inline/background assets отсутствуют. Rename/image/type/delete обновляют entry и выбор по UUID. Import создаёт и выбирает Object Card.|□|
|13|PNG400×200 с alpha размещается128×64; portrait crop не применяется. Move/resize/rotate/z/Undo сохраняют original image. После правки/удаления исходной Card размещённый raster сохраняет asset и геометрию.|□|
|14|Три слоя с перекрывающимися изображениями: front вверху списка; ↑ поднимает list и scene z, ↓ опускает, края disabled, выделен тот же UUID. Проверить Undo/Redo и restart.|□|
|15|Viewer+Editor одновременно: общий канон/Undo/tiles, разные камеры/selection, независимое закрытие/reopen; layer visibility/delete, object transforms, Escape отменяет drag, Space временно pan. Grid/world clipping/offset/zoom корректны, snap отсутствует.|□|
|16|Singleton Dice:7типов+modifier, формула/каждый результат/сумма/repeat/clear/copy/history50, narrow dock, без project dirty/Entity/presets; смена мира не создаёт копию.|□|
|17|Cards A/B + Table + viewer/editor + Dice: save→restart сохраняет UUID/refs/quantity/crop/sections/layers/objects/tokens/layout. Backup→новая restore-папка сохраняет канон+assets, без производных cells/tiles; отказ не перезаписывает существующую папку.|□|
|18|Настоящая большая PNG/JPEG/WebP, два Maps/1000tokens, cancel/error/rebuild, повторное открытие. Нет полного bitmap в GUI; действующие resource limits не сняты. Множество объектов не является SLA.|□|
|19|MOW sample: read-only preview/report→skip/remap→apply, source/aliases/safe HTML/media/links; исходники неизменны, исключённые поля отражены, prose не превращается в выдуманный инвентарь. Offline links/assets/traversal защита.|□|
|20|Dock all directions/CENTER/insert/float/redock/maximize→drag/focus/Tab, фиксированные боковые области;100/125/150% и mixed DPI/второй физический монитор. Синтетический DPR тест не заменяет это.|□|
|21|Распакованный новый ZIP в кириллическом пути на чистой Windows без Python: запуск и пункты1–20. Изоляция PATH на машине с установленным Python не закрывает ARU-64.|□|

## Проверенные границы

Автоматический frozen smoke создаёт временный Unicode мир, выполняет реальные commands/
Qt key events, refs/projections, Map library/layers, save/restart/backup/restore и layout.
Он не является визуальной ручной приёмкой и не подтверждает physical mixed DPI.
Полный snapshot writer/синхронный backup≤4GiB остаются; bounded worker/progress/cancel и
incremental changed-entity writer — отдельные следующие работы, не часть редизайна.

## Воспроизведение и ограничения

```powershell
.\LODANDSY.exe --self-test --report "$env:TEMP\lodandsy-smoke.json"
# опционально: --large-map-image "C:\Maps\large.jpg"
```

Это автоматический smoke во временном мире, не ручная визуальная приёмка.
Build из source: CPython3.14.8 x64 + requirements-build.lock,
`build_support/build_windows.ps1 -Python .venv/Scripts/python.exe -Archive LODANDSY-Iteration6-2026-11-19.zip`.
source/MANIFEST.sha256 и docs/validation/iteration6-frozen-source.json фиксируют
исходники и проверку compiled code; внешний SHA — соседний .zip.sha256. LICENSES и THIRD-PARTY.md в дистрибутиве.

Backup/restore пока синхронны,≤4GiB без tile cache; full snapshot writer остаётся.
Background backup/progress/cancel/incremental SQL — отдельные задачи. Source map≤2GiB,
cache≤4GiB/32768tiles, worker512MiB/900s, tileLRU64MiB, BMP/GIF≤16MP. Media64MiB/32MP,
thumbnail≤1024, documentLRU8MiB/shared16MiB/32pending. MOW≤500файлов/2MiB/64MiB total,
v1 subset. Эти пределы не являются SLA; реальные измерения и непроверенные пункты — отчёт.
