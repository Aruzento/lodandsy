# Windows portable — Cards / Actors / 5e14,21.11.2026

Стабилизированная сборка: `LODANDSY-Cards-Actors-5e14-2026-11-21.zip` и `.zip.sha256`
в `.prototype-deps`. Владелец принял итерацию7 в целом; точечная доработка ARU-46/78/84
и её проверки описаны в `docs/validation/2026-11-20-iteration-7-stabilization.md`.
Распаковать целиком в новую папку и запустить `LODANDSY.exe`. Python для запуска
не требуется по структуре frozen package; фактическая clean Windows приёмка этой
версии ещё обязательна. Прежний W2 preflight её не заменяет.

Текущий формат SQLite15/Card6/Map7/Actor1/Rules1/Table3, UI state4. Legacy/миграции отсутствуют;
старые проекты отклоняются без записи. Проверять на новом тестовом мире, исходные
пользовательские миры не удалять и не перезаписывать. Миграция тестовых данных не нужна.

## Сборка и проверка

```powershell
python -m pip install -r requirements-build.lock
powershell -File build_support/build_windows.ps1 -Python .venv/Scripts/python.exe -SkipPackage
.prototype-deps/mvp-dist/LODANDSY/LODANDSY.exe --self-test --report .prototype-deps/frozen-smoke.json
python -m build_support.verify_frozen --report .prototype-deps/frozen-source.json
python -m build_support.package_windows --archive LODANDSY-Cards-Actors-5e14-2026-11-21.zip
```

Locked stack: CPython3.14.8 x64/PySide6 6.11.2/Qt ADS5.1.1/pyvips3.2.0/
pyvips-binary8.18.7. Новых зависимостей нет. `THIRD-PARTY.md` и LICENSES включают
Qt/ADS/Python/libvips и native dependency notices; vips DLL SHA проверяется по provenance.
Пакет содержит точные исходники/тесты/docs/draw.io и source MANIFEST.sha256.
Папки references, private макеты/портреты, пользовательские проекты и кеши не публикуются.
MOW runtime исключён из исходников и проверяется как obsolete в compiled archive.

Автоматический `--self-test` обходит Welcome и использует отдельный временный мир
и отдельный QSettings catalogue. Проверяет Card/Map/Editor/Table/Dice, UUID hierarchy,
semantic keyboard input, shared resources, presentation/fog, layout и backup/restore.
Это не ручная визуальная приёмка и не clean Windows доказательство.
CI: полный suite на Windows QPA плюс targeted offscreen geometry/data/privacy;
для Windows offscreen tests регистрируется системный Segoe UI (font discovery там отсутствует).

## Ручной чек-лист:12исправлений+3новых возможности

В каждом пункте фиксировать: версия ZIP/SHA, Windows, monitor/DPI, результат и repro.
`□` означает, что владелец ещё не передал результат именно этой сборки. Автоматические
результаты отдельно в [итоговом отчёте](../docs/validation/2026-11-20-iteration-7.md).

|№|Сценарий и ожидаемое поведение|Результат|
|---|---|---|
|1|MOW: нет меню/import actions/source fields; обычные Card/aliases/HTML/assets работают.|□|
|2|Первый и повторный normal startup: компактный Welcome, Open/New, MRU last-used первым; мир сам не открывается.|□|
|3|Несколько миров с кириллицей/пробелами: Open сначала каталог title/path; другая папка регистрируется после успеха, case/relative duplicate не размножается. Missing/moved/locked/unsupported — ошибка, Locate или Remove только записи, файлы остаются. Cancel/fail не переключает текущий мир.|□|
|4|Gear icon-only у Inspector справа, tooltip«Настройки проекта», только работающие действия.|□|
|5|Backup/restore только в gear, без дублей верхнего меню; disabled без мира/busy. Dirty/invalid guards, cancel не меняет источник; восстановление в новую папку.|□|
|6|Создать все текущие типы Card; тип read-only над title. Rename/summary/typed fields сохраняются, тип после reopen прежний.|□|
|7|Ровно title в document tab и основной шапке, нет третьего title/breadcrumb; inline rename сразу меняет Tree/tab.|□|
|8|Summary редактируется inline, нет«…»/popup; Copy link доступна в Tree/context, URI entity/UUID работает.|□|
|9|Rich section/История/Описание: toolbar и текст у общего левого inset16px, нет пустой декоративной колонки; Table согласована с tabs.|□|
|10|Новая сетка25%, собственная opacity сохраняется; pan/zoom/DPI не сдвигают world grid и токены.|□|
|11|New Map→Editor: активен видимый«Слой1», сразу разместить Object Card. Reopen не добавляет слои; delete last→Undo/reopen корректны, явное добавление слоя доступно.|□|
|12|ПКМ токена «Открыть карточку»/«Копировать токен»/«Удалить токен». Удаление одного placement сохраняет Card/другие placements; undo возвращает. Broken reference диагностируется.|□|
|13|Монитор открывает отдельный player window одной карты; повторное нажатие фокусирует его. Нет ADS/toolbar/Inspector/scrollbars/context/drop/selection/tooltips. F11/double-click/Escape и перенос на второй монитор работают; reopen мира не запускает player автоматически.|□|
|14|Fog action показывает/скрывает компактную панель, не отключает player mask. Brush size в world units; polygon preview/close-first/Enter; invalid/self-cross/degenerate rejected, Escape отменяет; Space pan.|□|
|15|Erase пересекает brush/polygon/overlaps, оставляет holes/splits со стабильными IDs; topmost selection/Delete удаляет только region. Остальные overlaps скрыты. Один жест — один Undo/Redo; save/reopen/backup/restore сохраняют туман.|□|

## Обязательное дополнение Card Editor

|Проверка|Ожидание|Результат|
|---|---|---|
|Открыть3–5Card подряд, вернуться к каждой, повторно открыть активную|Portrait большой слева, справа type/title/summary; нет скачка header/портрета, вкладки под общей шапкой.|□|
|Portrait и empty portrait, первое открытие и завершение загрузки|Квадрат132–220logicalpx, аккуратный aspect/crop, геометрия не меняется от изображения.|□|
|Короткий/длинный title, короткое/500-char summary|Title читается крупно; summary inline, без popup/дублей. Короткая карточка не требует scroll только из-за шапки.|□|
|Узкий/широкий dock, floating, resize высоты/ширины|Размер header зависит от ширины, нет лишней левой колонки/пустой строки/обрезки controls; стабильная компоновка Qt Widgets.|□|
|Переключить rich_text/inventory/table tabs, затем reopen проекта|Портрет/header стабильны; content/caret/scroll/Undo и дочерний inventory сохранены.|□|

## Отдельные конфликты, синхронизация и Windows

|Сценарий|Ожидание|Результат|
|---|---|---|
|B commit(finish=False)/Ctrl+S, A conflict, Escape/cancel B, затем blur|Канон B и чужой draft A сохраняются в Card и embedded/standalone Table. UseSaved/ApplyMine доступны до явного решения.|□|
|Редактор открыт на старом draft, другой редактор публикует новый draft или меняет observed value|Cancel старого редактора не очищает и не восстанавливает более старый draft/status.|□|
|Одно поле Card в Editor/Inspector: A draft, B saved, A conflict; reopen/blur/unchanged Enter/Ctrl+S|Канон B сохранён; raw A остаётся конфликтом, нет silent overwrite; другие валидные изменения autosave.|□|
|UseSaved и ApplyMine, затем третья canonical правка C до применения|UseSaved не пишет; ApplyMine требует повторного разрешения после C. Escape/close/discard согласованы, stale owner не применяет старый raw.|□|
|Одна Table embedded/standalone, оба порядка передачи фокуса; number/entity picker conflict|Оба views показывают conflict actions; reopen/flush не перезаписывает B. Активный ввод, Undo/caret и background save ACK сохраняются.|□|
|Редактировать quantity в embedded Table, параллельно изменить summary Card|Delegate/raw не исчезает и не делает преждевременный commit. Rich invalid draft discard возвращает канонический document.|□|
|Player другого aspect/DPR, pan/zoom/fit GM, объекты вне фона|Player следует тем же visible world bounds с чёрным letterbox, не показывает дополнительную территорию; нет feedback/dirty от камеры.|□|
|Token/object drag/escape/Undo, скрыть слой из Editor|Player получает transient/live changes, нет SQL/revision на каждую точку; один commit в конце и откат при cancel; скрытые слои не видны.|□|
|Скрытый token частично за fog, overlap/hole, provisional erase; загрузка/нет asset/switch мира|Player100% black поверх всех items; нет швов/проблеска скрытого фона/GM alpha/временного reveal. До current map+fog+camera только чёрный.|□|
|Закрыть player, Viewer, Editor, удалить Map, сменить мир, shutdown|Соответствующий lifecycle без потери канона/других документов, без поздних callbacks и лишнего focus-out в новом editor.|□|
|Два физических монитора, разные DPI, fullscreen/exit, disconnect monitor|Адекватный размер/кадрирование; нет off-screen недоступного окна, фокус и ввод GM сохраняются.|□|
|Большая реальная карта233MP,1000tokens/30objects/64regions, два окна|Оценить фактическую плавность pan/drag/fog и RAM, reopen/close; автоматические timings не равны SLA.|□|
|Чистая Windows без установленного Python, именно новый ZIP|Запуск, import большого изображения/native vips, Card/Map/Table/Dice, presentation/fog, save/backup/restore. Отдельный обязательный ARU-64.|□|

Ограничения сохранены: full snapshot writer, synchronous backup≤4GiB; на233MP
профиле backup блокировал GUI~0.87s. TileLRU общий64MiB, source≤2GiB/cache≤4GiB/
32768tiles/worker≤512MiB/900s. Fog≤256regions/8192points-region/65536total,
512samples-gesture/8MiB JSON; oversized gesture отклоняется целиком с объяснением.
Manual visual/physical mixedDPI/clean Windows не помечать Done по offscreen/native Qt tests.

## Дополнение приёмки Cards / Actors / 5e14

Новый кандидат заменяет предыдущий ZIP, приёмка относится только к его SHA256.
Результаты автоматизации: docs/validation/2026-11-21-cards-actors-5e14.md.
SRD5.1 attribution включена в LICENSES/SRD-5.1-NOTICE.txt и source/build_support.

|Физический сценарий нового ZIP|Ожидание|Результат|
|---|---|---|
|Создать Player, открыть два Viewer/Inspector, изменить HP/name/active inventory|Общее состояние без сброса фокуса/каретки; разные карты синхронны.|□|
|Десять NPC одной Card; copy раненого7/20|Независимость, копия20/20 и template inventory; Undo не откатывает чужое состояние.|□|
|Tree base / Token Actor / Item Inspector; «Связи» без размещений|Контекст и владелец ясны, participant доступен после удаления последнего token.|□|
|Включить/выключить Player, choose existing/new и Cancel|Предупреждение, старые refs/state неизменны, Cancel ничего не пишет.|□|
|Два Actor inventories, Item +2 CON и qty8|Только active actor получает бонус один раз, max HP меняется44→49, live cost/description.|□|
|Rules editor draft/test/preview/apply/reset/ошибка; manual HP/AC/speed|Нет записи до apply; ошибки/stale видны; final manual не затирается.|□|
|Formula clamp уменьшает current; autosave/backup/reopen|Все UUID/активность/rules/manual сохраняются; рост max не лечит.|□|
|Узкий dock и floating; Tab/Enter/blur/Escape/Ctrl+S, конфликт двух представлений|Ввод и чужой draft сохраняются, нет broad scene/header reset.|□|
|GM/Player на двух физических мониторах, mixed DPI, fullscreen, blackout|Без скрытых данных/проблеска, фокус GM сохраняется; прошлый preflight не доказательство этой версии.|□|
|1000 independent actors/1000 shared placements|Фактические pan/zoom/ввод и задержки оценены человеком, автоматические timings не SLA.|□|
|Чистая Windows без Python, новый полный ZIP, Unicode path|Запуск/native libvips/save/restart/backup/restore; ARU-64 остаётся открытым до результата.|□|

Старые schema14 worlds не открываются: использовать новый disposable тестовый мир,
не удалять реальные проекты. Physical checks здесь не выполнены автоматически.
