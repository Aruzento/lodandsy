# LODANDSY — инструкции для Codex

## Цель и источники

LODANDSY — нативное локальное Windows-приложение для ведущего настольных ролевых игр. Доведи продукт до проверяемого MVP, описанного в `docs/MVP.md`. Главный результат — удобная рабочая среда, где несколько карточек, карта и инструменты сосуществуют, а данные надёжно сохраняются. Не превращай MVP в полный VTT.

- `docs/MVP.md` определяет продуктовые требования, критерии приёмки и явно обозначенные предложения, требующие согласования.
- Linear — источник плана и состояния задач. ADR (записи архитектурных решений) фиксируют принятые существенные решения. Код и тесты — источник фактического поведения, а не доказательство того, что оно верно по продукту.
- При противоречии между требованиями, ADR, Linear и кодом покажи расхождение; не меняй продуктовый контракт молча. Указания владельца продукта имеют приоритет.
- Работай на русском в отчётах, комментарии и имена в коде — по существующему стилю проекта.

## Роли и автономность

Владелец определяет продуктовый результат и принимает решения, меняющие UX, формат данных, безопасность, стоимость или границы MVP. ChatGPT помогает уточнять архитектуру и проверять результат. Codex исследует репозиторий, предлагает и реализует технические решения, пишет тесты, устраняет регрессии, обновляет документацию.

Не спрашивай разрешения на каждую мелкую правку. Самостоятельно выполняй согласованный функциональный блок до результата. Останавливайся на существенном неподтверждённом продуктовом решении или необратимом действии, а не на каждой локальной задаче. Можно продолжать независимые части, пока ожидается решение. Не делай commit/push, merge, release, удаление пользовательских данных или изменение публичного формата без явного разрешения. Не уничтожай чужие незакоммиченные изменения.

## Архитектурные ограничения

- Общее правило владельца: не сохранять устаревшие решения без обоснованной текущей
  необходимости. Общее правило разработки: разрешена потеря тестовых данных: legacy Markdown,
  старые редакторы/режимы/форматы и адаптеры совместимости удаляются. Обязательные
  миграции и архивирование старых форматов отменены. Единственный формат Card — новый
  визуальный документ ADR-014; единственный URI — lodandsy://entity/UUID. Старые проекты
  не изменять автоматически: неподдерживаемая версия получает явный отказ. Это правило
  имеет приоритет над историческими требованиями обратной совместимости ниже и в ADR.
- Сохраняй Python 3.14, PySide6, Qt Widgets и Windows-first. Изменение основного стека требует доказанной необходимости и согласования. Не вводи web runtime, сервер, облако, второй GUI-стек, ORM, плагинную платформу или новую зависимость без конкретной причины и проверки совместимости, лицензии и сборки.
- Модульный монолит: `domain` — данные и инварианты без Qt; `application` — операции, сессия, координация сохранения и адаптеры; `ui` — Qt-представления и оконная политика. Не перестраивай каталоги ради формальной архитектуры.
- Маленький Core, встроенные Cards, Map, Tools. Модуль владеет собственным payload и операциями; общий Entity contract минимален. UI не владеет данными мира. Один путь изменения на объект и один канонический источник истины для сохранённых данных.
- Отдельно храни выбор в Tree, идентификатор открытого документа, активное окно и локальное состояние интерфейса. Несколько представлений не создают независимых копий данных. Уведомления адресные, по ID; не полагайся на ручной refresh нескольких отдельных компонентов.
- ID стабилен, parent существует или отсутствует, циклы и дубликаты запрещены, перемещение и порядок валидируются в домене; неизвестный kind/версия не приводят к потере данных. Ссылки между объектами не смешивай с иерархией.
- Принято владельцем 18.11.2026: S3 — одна каноническая SQLite на проект через sqlite3 без ORM, assets отдельно с относительными путями; S1 параллельно не поддерживается. Card хранится в единственном визуальном формате ADR-014; экспорт за пределами MVP. Foreign keys на каждом соединении, составные операции транзакционны, TokenInstance обязательно ссылается на Card; удаление Card с подтверждением атомарно удаляет её размещения, неожиданные broken references диагностируются.
- Сохранение: один pipeline для autosave и Ctrl+S, состояние dirty/saving/error, упорядоченные ревизии, ошибки видимы, безопасное закрытие, резервные копии и восстановление. Индекс и кеш производные, если выбран файловый формат. Не объявляй атомарную запись одного файла транзакцией всего проекта.
- Обязательный W2 preflight успешно пройден владельцем 18.11.2026: Windows без Python, docking/insert/float/maximize→drag/layout/DPI/мониторы. Разрешённая миграция выполнена; совместимость и лицензии зафиксированы в ADR-002 и build_support/THIRD-PARTY.md. Сквозную ручную приёмку новой полной сборки Map/Tools учитывай отдельно.
- Tree/Inspector — фиксированные панели; рабочие документы и инструменты имеют независимые окна. После успешного ручного preflight владельца принят W2: Qt ADS 5.1.1 / PySide6 6.11.2. ADS владеет размещением, WindowManager — жизненным циклом; предметная модель не зависит от ADS. Не возвращай заменённый самописный docking. При обновлении Qt/ADS повтори обязательные сценарии и проверку сборки.
- Qt-виджеты изменяй только из GUI-потока; долгие операции отделяй при доказанной необходимости. Никакого `eval` для пользовательских выражений.

## Рабочий цикл

Итерация7 в целом принята владельцем. Финальная стабилизация ARU-46/78/84:
docs/validation/2026-11-20-iteration-7-stabilization.md. Новая разработка ведётся
от стабильного main отдельными функциональными модулями по задачам Linear.
Утверждённый контракт7 и прямое дополнение о Card Editor остаются обязательными.
ADR-027 сохраняет независимых владельцев Cards/Tables/Maps/Dice. Core/Resources/Media/
navigation и transactional ProjectActions собираются только composition root. Никаких
private widgets/worker соседних модулей и общих ModuleController/ModuleSession.
Один canonical EntityCollection/SQLite writer и post-commit revision ACK.

MOW parser/controller/actions/source fields отменены и удалены. Общие aliases, HTML
sanitizer и assets сохраняются. Welcome/Open используют MRU каталог QSettings вне мира;
ProjectController выполняет guards, неудача не переключает мир. Backup/restore — gear
правого rail. Не создавать сканер миров или второй формат хранения. ADR-030.

Обязательный Card Editor: square portrait слева132–220 logical px; справа immutable
read-only type, один title и inline summary. Ниже отдельный ряд tabs и content inset16px.
Никаких breadcrumb, summary popup, centered prose gutter или дублирующей шапки.
Геометрия зависит от ширины, не от содержимого/активации/высоты; header/hero/metadata
имеют согласованную рассчитанную высоту. Тип выбирается только при create и защищён
также при generic payload replacement. Rich text — непрерывный QTextDocument;
coalescing250ms/max2s, generation/section UUID управляют временем жизни callbacks.
Structured input commit Enter/Tab/blur/Escape/Ctrl+S, не каждая буква. Conflict draft
не становится authoritative после reopen/blur/flush: явные UseSaved/ApplyMine,
проверка нового canonical value; валидные данные сохраняются независимо. ADR-032.
Cancel/Escape восстанавливает только своё поколение draft, не очищает и не возвращает
чужой более новый черновик; raw/base/observed/error восстанавливаются согласованно.
В test_module_boundaries каждый runtime-файл имеет явного владельца; проверки всех
feature helpers, presentation/fog и relative imports обязательны при модульной разработке.

Maps владеет Viewer/Editor/Presentation и FogState в единственном MapPayload/SQLite.
MapView roles разделяют сцены и overlays, но используют общий канон и bounded tile/media
providers. Player top-level, не ADS и не layout state; camera следует Viewer с letterbox,
никакого расширения world framing. До coherent map/fog/camera — чёрный экран.
Первое открытие не забирает GM focus; повторное фокусирует существующее окно.
Только committed fog на player,100% black поверх tiles/grid/objects/tokens;
GM default50%. Numeric rings/UUID, bounded geometry и Qt adapter, без bitmap всей карты.
ADR-031. Незавершённые gestures остаются локальными; один жест — одна Map Undo команда.

Qt дизайн нейтральный graphite #191919/#202020. Private макеты/портреты остаются
только в .prototype-deps, не repo/production/release. Inventory — обычная Table:
item UUID, positive integer count, live description/cost без stored derived cells.
Object Cards library, original alpha/aspect long-edge128; front layer сверху.
Full snapshot writer/synchronous backup4GiB и libvips tiles сохраняются.
Схема по факту: SQLite16/Card7/Map8/Actor1/Rules1(profile2)/Table3, UI state4; legacy/migration adapters нет.
Targeted batches после блоков, общий gate/build после стабилизации; report/draw.io/checklist.
Git-действия только в конце после проверки по последним указаниям владельца.

## Проверки и отчёт

Команды из текущего README (проверь актуальность в checkout):

```powershell
python -m lodandsy.main
python -m pytest
python -m ruff check .
python -m pip check
```

GUI-тесты pytest-qt и offscreen не заменяют ручную проверку Windows: focus, docking, floating, maximize/restore, mixed DPI, второй монитор, установленная сборка. Не заявляй о запуске тестов или сборки без фактического результата. Не считай количество тестов эквивалентом качества.

Каждый отчёт о блоке: цель и ID Linear; изменения и затронутые файлы; команды и фактические результаты; что проверено и не проверено; риски и решение владельца (если нужно); состояние задач и следующий блок. Если есть блокер, укажи точную причину и условие продолжения. Продолжай до согласованного результата, а не до первой компилирующейся версии.

## Cards / Actors / Variables / 5e14 (21.11.2026)

Утверждённый пакет A–I и ADR-033 расширяют итерацию7. CardPayload owns immutable
ActorState/default; Actor не Tree Entity, Token ссылается на Card+Actor. Только
Character/Creature/Object создают Actor. Player toggle не перепривязывает существующие
размещения; NPC copy получает нового Actor и template inventory. Последний token/map
не удаляет состояние. Actor inventory — отдельная обычная Table с явной активностью.
Item modifiers применяются один раз на row/modifier, qty не множитель; soft refs
диагностируются. Maps читает participant DTO, не владеет HP. Core хранит opaque settings;
правила 5e14 и bounded AST evaluator принадлежат Cards. Никакого исполнения AST.
Manual HP/AC/speed final; снижение effective max атомарно clamp current, рост не лечит.
Формулы применяются только после preview с revision+state serial, не на каждую букву.
Универсальный конструктор переменных, полный combat/effects/slots, multiclass HP,
scalar/delete Undo и межкартовый перенос отложены. Только адресованная история map.
Физическую приёмку нового ZIP и ARU-64 не объявлять пройденными по native Qt smoke.

Дополнение UI-приёмки A–F / ADR-034: прежнее «характеристики только Inspector» отменено
владельцем. Cards-owned виртуальные страницы Характеристики/Модификаторы используют
те же FieldEdits/ValueAddress, без Section и изменения тогдашних SQLite15/Card6/UIstate4. Явный
контекст база/Actor, просмотр не создаёт участника. Технический Card Inspector и
оперативный Actor/Map Inspector разделены. Русский UI catalog не меняет domain IDs;
qtbase_ru входит в сборку. Typed Item dialog/история по уровням/примеры формул вместо
пользовательского JSON. Правила — один native dialog текущего проекта из gear, guarded
preview/apply. Отчёт/матрица: docs/validation/2026-11-21-ui-acceptance-fix.md и
2026-11-21-ui-fields.md. До ручной приёмки ARU-65/80/83 остаются В работе. Commit/push/
merge/release этим пакетом не разрешены. Частные вложения не включать в source ZIP.


Дополнение 22.11.2026 — лист персонажа v2 / ADR-035: inline ability scores, 3/2/1
блоки с 18skills/6saves, homebrew race/class/subclass/level. Item equipment facts
определяются только active inventory rows, один armor/shield с atomic replace/cancel.
Card armor_type/armor_base/shield удалены; это только resolved formula inputs.
SQLite16/Card7, профиль5e14 version2; legacy/миграции отсутствуют по новому прямому
решению владельца «все миры тестовые». SQLite15 отклоняется без записи/удаления.
Ручной итоговый AC побеждает, оборудование и источники видны в native AC dialog.
Отчёт: docs/validation/2026-11-22-character-sheet-v2.md. Новые Git-публикации не разрешены.

Maps M5 /25.11.2026 /ADR-036: Maps owns immutable shapes/portals in Map8, читает
Map7 с пустыми новыми коллекциями без записи на open. SQLite16/Card7 неизменны.
Фигуры+подписи публичны ПОСЛЕ fog; handles/previews/portals GM-only. Стрелки и
original-image overlays transient, hidden movement data не передаётся Player.
Inspector feature-page API нейтрален, composition root координирует владельцев.
Commit/push текущего M5 разрешены владельцем после проверок; merge/release отдельно.
Матрица и поставка: docs/validation/2026-11-25-map-m5.md.
