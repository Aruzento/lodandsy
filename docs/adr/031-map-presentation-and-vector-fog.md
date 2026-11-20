# ADR-031 — общая карта, презентация и векторный туман

Принято в утверждённом пакете7. Владелец — MapsController/MapsService, Core не знает
о ролях экранов. Один MapDocument/MapPayload и существующий SQLite snapshot writer.
Новых зависимостей, хранилищ или копий канона нет. Tile pyramid и общий bounded
MapTiles LRU остаются прежними. Presentation — отдельное native top-level окно,
один экземпляр на map ID, не ADS document и не часть сохраняемой раскладки.

Раздельные role-specific MapView scenes используют один renderer и общие decoded
tiles/media. Player не содержит input/edit/tooltip/selection UI. Камера следует
MapViewer; иной aspect сохраняет исходный world rectangle, остальное закрывает
непрозрачный letterbox. До coherent map+fog+camera frame вывод полностью чёрный.
Смена проекта/удаление карты/закрытие Viewer закрывают presentation и connections.
Transient drag по ID не меняет канон/ревизию до завершения жеста.

FogState содержит FogRegion(UUID, rings) в координатах мира. Rings — числовые
замкнутые контуры с odd-even fill; holes и disconnected components сохраняют ID.
Qt-free domain проверяет типы/конечность/бюджет. Application adapter использует
QPainterPath united/subtracted и toSubpathPolygons, не bitmap карты и не собственный GIS.
Контрольный Qt6.11.2 prototype: subtraction внутреннего круга сохранила hole через
ring roundtrip; поперечное вычитание вернуло два компонента. Не используется
toFillPolygons с rewinding bridges. [Qt API](https://doc.qt.io/qt-6/qpainterpath.html#toSubpathPolygons).

Лимиты:256 regions,8192 вершин/region,65536 всего;512 samples/gesture и512 polygon
vertices. Превышение отклоняет всю команду с сообщением. Brush — capsule union,
erase вычитает из всех пересечённых regions. Один завершённый жест — один Map Undo.
Player получает только committed fog. GM opacity50%, player100% black; player fog
рисуется foreground поверх tiles/grid/objects/tokens без antialias раскрытия края.
Fog редактируется во всём world viewport, включая внешние области объектов.
Панель инструмента — локальная UI видимость и никогда не выключает canonical fog.

Map6 включает fog и persisted layers_initialized. Новая карта атомарно получает
видимый «Слой 1». Первое открытие editor инициализирует незавершённый документ один
раз; удаление последнего слоя не вызывает его повторного создания.
SQLite14/Card5/Map6 — один актуальный формат; прежние версии отклоняются без записи.
Полные raster/render/lifecycle/performance результаты фиксируются после реализации.


## Фактическая реализация и измерение

MapDocument/MapPayload6 по умолчанию создают видимый «Слой1»; explicit layer edits
фиксируют initialization, а first-open init относится только к незавершённым данным.
Renderer не делает глобальные Boolean unions на каждый view: Qt simplified
нормализует каждый odd-even region (включая intersecting loaded rings), затем
ориентация outer/hole даёт nonnegative winding union. Тесты сравнивают с исходной
семантикой region union, включая обратную ориентацию и самопересечения без cancellation.
MapsController держит один derived compiled path на открытый map/fog snapshot,
делит его между ролями и удаляет после последнего документа/reset. Это не второй канон.

Нативный233MP профиль Windows:1000tokens/30objects/64regions, общий tile cache
66,852,864bytes (<64MiB), GUI peak190.32MiB/worker157.27MiB. Fog gesture p50/p95
115.012/157.738ms после исправления повторных unions (первый профиль368.063/760.188ms).
Два render+pan surfaces p50/p9530.399/85.921ms; transient0.050/0.145ms без ревизий.
Import15.964s/reopen4.004s, save137.709ms, synchronous backup872.016ms.
Player close RSS190.05→184.59MiB. Это не SLA и не физическая оценка плавности;
baseline6 измерял один explicit render без полного двухоконного event processing.
Оба доступных экрана96DPI; mixedDPI не подтверждён. Подробности — итоговый validation report.

Presentation — independent top-level без QWidget parent AppShell. WA_ShowWithoutActivating
на первом показе предотвращает поздний native focus-out, закрывавший следующий Table
editor; повторный open явно activateWindow. Регрессионный native test прошёл без задержек.
