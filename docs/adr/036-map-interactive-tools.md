# ADR-036 — интерактивные инструменты Maps M5

25.11.2026. Утверждённый владельцем пакет ARU-87–90, решения R1–R7.
Baseline локальной принятой полировки: fee0106 + незакоммиченные v2/polish изменения.
Не заменять их старым main. Commit/push разрешены после реализации и проверок;
merge/release не следуют из этого разрешения.

Maps сохраняет единственный MapDocument/MapPayload и адресованную component-delta
историю MapEdit. Фигуры и порталы — immutable map-owned UUID records, не Entity.
Создание, transform/style/vertex edit/delete проходят MapsService и итоговые
валидаторы, не прямую запись из Qt. Пределы:10000 records/map,512 vertices/shape,
finite bounded coordinates, positive dimensions; self-intersection запрещена.
Круг и конус масштабируются равномерно. Конус: base width=length.

Расстояние — чистая world-space функция с явной метрикой; сетка использует max(dx,dy),
геометрия hypot. Без snap свободное движение геометрическое. F берётся только из
MapGrid.feet_per_cell, при None честная диагностика. Размеры фигур геометрические.
Предпочтение режима — существующий UI settings, не копия калибровки. Transient drag
привязан к map/session/token, origin immutable, destination реальная preview-position;
нет writes на кадр и нового Undo. Player получает лишь полностью публичный сегмент;
unknown visibility fail closed. Видимость перепроверяется при изменении fog/layers.

Рендер: фон/объекты/сетка/токены/публичная стрелка, затем opaque fog, затем только
committed public shapes+labels; GM handles/previews/portals никогда не Player.
Opacity shape над fog смешивается с чёрным, не вырезает fog. Hit testing GM не
передаёт hidden token metadata в public representation.

Портал — soft UUID reference существующей карты, self-link отвергается, удалённая
цель диагностируется и перепривязывается. Double-click открывает GM и retargets уже
открытый Player в том же top-level окне; blackout до coherent tiles/fog/camera,
generation guards/disconnect старых callbacks. Не создавать Player автоматически.

Portrait: один transient controller для GM/Player, original resolved asset override,
без crop/рамки/служебных labels. Скрытое изображение публикуется только после native
подтверждения. Existing bounded media provider, fit aspect, asynchronous readiness,
idempotent synchronized close, generation guards; нет сохранения/Undo.

Хранение расширяется в существующем SQLite snapshot writer атомарно. Реализован
Map8: существующая JSON-колонка objects содержит envelope objects/shapes/portals.
SQLite16/Card7 неизменны. Map7 читается с прежним списком objects и пустыми новыми
коллекциями; чтение не пишет в файл. Обычный следующий save явно пишет Map8.
Никакого копирования базовых значений, второго writer или скрытой миграции.
Старый EXE отвергает Map8 до записи; текущий отвергает неизвестный Map9.
Совместимость с актуальными SQLite16/Card7/Map7 мирами проверена hash/load тестом. Неподдерживаемые файлы не перезаписывать.

Источники: Basic Rules2014 Combat (Playing on a Grid) и Spellcasting (Areas of Effect),
https://www.dndbeyond.com/sources/dnd/basic-rules-2014/combat и
https://www.dndbeyond.com/sources/dnd/basic-rules-2014/spellcasting проверены browser.
Это не автоматизация боя/попаданий/маршрутов. Никаких новых dependencies/ORM/EventBus.

Проверки: targeted B/C/D/E; финальный native+offscreen, Ruff/pip/diff/architecture,
source/frozen/portable/parity, actual Qt pixel/DPR evidence, сравнительный профиль
и ZIP manifest/SHA. Matrix D/S/P/V/G из пакета — требования, не доказательства.
I5/clean Windows и физическая приёмка M5 отдельно. Linear не закрывать до приёмки.


Inspector предоставляет нейтральный show_feature_page; composition root завершает
семантический ввод прежнего владельца и показывает Maps-owned panel. Binding Cards
не перехватывает активную feature page при фоновом refresh; явный выбор документа,
Actor или смена проекта возвращают обычный Inspector. Domain от этого не зависит.
Для массовой отрисовки Maps держит ограниченный текущими UUID производный кеш path/
transform/style/label, не медиакеш и не второй канон. Public shapes рисуются только
после fog. Метрика без snap явно непрерывная max при выбранном grid, hypot при
geometry, без округления world coordinates. QSettings maps/measurement — UI preference
вне мира. Circle/cone resize uniform; Shift удерживает центр bounding box, обычный
resize — противоположный якорь; Alt uniform для произвольных полигонов.

Дополнение v0.01 / ARU-77. В режиме «Выбор» у одного выделенного токена
карточки «Объект» рамка и угловые ручки используют общую геометрию якоря
и оформление ручек фигур. Отдельная ручка поворачивает вокруг центра, Shift
квантует угол с шагом 15°. Масштабирование работает в локальных координатах
исходного положения, сохраняет смещение точки захвата и держит противоположный
угол. Shift удерживает центр, Alt оставляет отношение сторон, можно совместить.
Размер хранится в дробных клетках с точностью float, без шага и заданного минимума.
Защищены представимость, положительный размер и технический предел геометрии карты.
Изображение вписывается в повёрнутую рамку с исходными пропорциями и прозрачностью.

Escape отменяет локальный предпросмотр. Один завершённый жест записывает
трансформацию `TokenInstance` одной командой Map Undo. Hit-test использует
повёрнутую форму. Для движения под туманом учитывается площадь, которую заметает
повёрнутый footprint. Презентация получает итоговую геометрию под туманом.
Рамка, ручки и предпросмотр принадлежат только Viewer.

Map10 хранит дробные `cells_w/cells_h` и `rotation`. SQLite17 сохраняет
прежние таблицы. Версии Map7–9 читаются без записи и дают угол 0°. Карты без
новой геометрии продолжают сохраняться в Map9. Перед первым сохранением Map10
в существующем мире или переводом ещё одной ранее сохранённой карты приложение
публикует `LODANDSY-before-Map10-*.lodbackup` рядом с папкой проекта и проверяет её
временным восстановлением. Запись и проверка результата выполняются в одной
транзакции SQLite. Приложенные файлы сохраняются на прежних путях. После перехода
карта остаётся Map10, в том числе после Undo к целочисленным размерам.
[Политика совместимости](040-managed-projects-v001.md)
