# ADR-016 — единый токен и видимая мировая сетка

Итерация4: актуальные payload/поля/шаблоны/размещения/кеши — ADR-019…022. Противоречащие части этой записи являются историей; безопасный Qt HTML, S3 и текущий стек сохраняются.
ARU-77, заменяет модель ADR-012. Map payload v3 / SQLite schema8, один MapToken:
UUID/title/kind character|item/optional asset_id/entity_id/x/y/cells_w/cells_h/z.
MapPin и старые pixel sizes удалены без миграции по прямому решению владельца.
Ссылки разрешаются общим Entity registry; отсутствие цели/картинки не удаляет токен.

Координаты — центр в пикселях исходной карты; footprint — целое1..100 клеток по оси.
Размеры renderer выводит из cell_size, изменение сетки не перемещает центры. Snap
выравнивает верхний левый угол footprint к границам клеток (правильно и для2×2).
Центр ограничен границами исходника; на краю часть footprint может выходить за изображение.
Character: центрированный квадратный crop, clip кругом, белая косметическая рамка.
Item: aspect fit с alpha, рамка только при выделении. Без image — placeholder той же модели.

Сетка включена по умолчанию, color/opacity/offset/cell/snap доступны. Dual black+color
контур виден на светлом и тёмном фоне. При дальнем zoom показывается каждая2^N линия,
а не скрывается вся сетка; математический шаг и snap не меняются. Рисуется только viewport.
Сохранены incremental ID items/selection, per-map Undo200, общий bounded thumbnail cache,
неизменённые libvips worker/тайлы. Renderer/domain не зависят от ADS/SQL друг от друга.

Проверки: world drag при zoom0.5/2, snap1×1/2×2, смена cell без движения, Undo/delete,
ссылки/битые ресурсы, круг/белая рамка/item aspect alpha, far LOD, текущий save/backup.
Реальный NASA21600×10800 (233MP), две карты,1000tokens: импорт17.727s, reopen6.055s,
GUI peak168.52MiB/decoder163.84MiB, render p50/p95 2.81/4.79ms, tileLRU64MiB,
до30видимых тайлов. Максимальный event-loop gap1516.56ms включает import/save/reopen;
это не доказательство ручной плавности, native UI/DPI приёмка остаётся G.
Пересмотр при измеренной потребности других footprints/shapes; боевых правил нет.
