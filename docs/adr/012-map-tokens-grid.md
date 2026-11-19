# ADR-012 — Map tokens и квадратная сетка

19.11.2026, ARU-71. Граница утверждена владельцем в REQUIREMENTS следующей итерации:
самостоятельные image tokens и square grid без игровых правил. E сначала реализован
и проверен, после чего начат F. Новый RPG entity kind не нужен.

MapDocument дополняется immutable MapToken(title,asset_id,x,y,width,height,z,id,card_id)
и MapGrid(enabled,cell_size,offset_x,offset_y,opacity,snap). UUID стабилен. Tokens/pins
не имеют повторяющихся ID внутри карты; несколько tokens могут ссылаться на одну Card.
Card UUID и asset UUID — ссылки, payload не копируется. Удаление Card и недоступный
asset не уничтожают token. Pins остаются прежними нормализованными координатами;
tokens/grid используют пиксели исходного raster, независимо от LOD/zoom/DPI.

Создание/import и замена изображения используют тот же bounded immutable asset adapter,
что Cards: signature/decode64MiB/32MP, относительный assets, SHA dedup, общий saver.
UI token painting запрашивает видимые thumbnails из общего LRU16MiB; каждый token
не удерживает отдельный полный QImage. Missing/corrupt image — красная заглушка и
tooltip; broken Card — диагностика, переход остаётся внутри application layer.

Snap действует при создании/drag к центру клетки; центр ограничивается границей
raster, включая неполную крайнюю клетку. Выбор, resize, смена grid size/offset/visibility
или zoom никогда не изменяют существующие координаты. Grid enabled — только показ,
snap может работать при скрытой сетке. При cell<5screenpx линии не рисуются, мировая
сетка/snap не меняются. Линии ограничены viewport/2048наось. Token properties меняют
title,size,z,Card; context menu также даёт open/createCard/unlink/replaceImage/delete.
Per-map QUndoStack сохраняет целую immutable операцию. При недоступном фоне spatial
drag токенов отключён, их data/properties сохраняются.

SQLite schema4: к map_document добавлены tokens/grid JSON columns; Map payload2.
Migration v3→v4 — ALTER TABLE/empty defaults/version в одной транзакции после DB backup.
Схемы1/2 сначала получают прежнюю M1 migration, затем4. Неизвестная версия/поле
безопасно отклоняется до переписывания. Старый executable откажет при schema4, что
предотвращает потерю tokens. Это один canonical SQLite формат с upgrade, не два store.
Token asset/Card ссылки внутри payload допускают отсутствие цели для диагностики;
SQLite foreign_keys по-прежнему ON для всех соединений. Map background FK прежний.
Backup/restore включает SQLite и исходные assets, tile cache перестраивается.

Проверяются domain invariants/duplicate IDs, grid/snap/noop/Undo, реальные Qt drag
на разных zoom, создание и properties через UI, две связи на Card, missing images,
save/restart/backup, migration backup/rollback/future fields. Native DPI/мониторы и
итоговый дистрибутив — отдельная ручная приёмка, не заменённая Qt-тестами.
Пересмотр при утверждении других координат/форм сетки или игровых возможностей.

Реализация сохраняет QGraphicsItem по UUID при изменении token/grid: selection и
drag не теряются, неизменные pins не перестраиваются. No-op snap возвращает view
к canonical позиции без дополнительной Undo-команды. File lookup token images
кешируется на250ms (только metadata keys, не дополнительные QImage вне LRU).
При1000tokens на NASA233MP: GUI167.81MiB, decoder157.36MiB, render p50/p95
1.12/2.95ms, tileLRU64MiB/max30visible. Начальная вставка1000объектов дала timer gap
381.48ms; это ограничение bulk initialization, не обещание бесконечной сцены или SLA.
Измерение автоматическое, Native input/DPI остаются в ручной приёмке.

Superseded: ADR-016 заменяет MapPin/пиксельные размеры единым токеном. Legacy/migration отменены владельцем.
