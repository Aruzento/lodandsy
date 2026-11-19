# ADR-022 — media working set и границы snapshot writer

ARU-75/78/45/46/47/52/54/70/77/81, утверждённая стабилизация G.

Дефект подтверждён исходным кодом: RichDocument резервировал4MiB на каждое pending image
и после8MiB возвращал null QImage, помечая последующие валидные изображения unavailable.
Увеличение числа не решает проблему. Теперь intrinsicSize использует только bounded metadata
через QImageReader.size; bitmap запрашивается в drawObject видимой области. Document LRU8MiB
вытесняет и повторно запрашивает, pending None не равен unavailable null QImage. Shared
CardImages16MiB/128entries,32pending jobs; document16entries. Immutable QImage implicit sharing
не копирует pixels. На закрытии/смене section bitmap refs освобождаются, QTextDocument/Undo/
курсор остаются. TTL250ms проверяет stat, project generation отвергает stale callback;
старые pending не сбрасываются из общего счётчика до completion, очередь не растёт при
переключении проектов. Metadata LRU256entries. Тест20различных1024² изображений проходит
вперёд/назад/close/reopen, проверяет бюджеты и неизменность source. Большой фон не идёт сюда.

Table: замер текущего интегрированного UI выявил полную100k-cell value validation и
whole-table dataChanged на каждый ввод. RowRecord immutable; private derived proof cache
помнит одну tuple(columnID,type) схему. Только неизменные успешно проверенные scalar cells
повторно используются; replace(row) сбрасывает proof, schema change проверяет заново.
Глобального кеша старых проектов/дублирования данных нет, proof не сохраняется в SQLite.
Структура/порядок/UUID проверяются всегда. ModuleSession принимает validated RandomTable
без повторного replace, проекция переиспользует тот же immutable объект. Model dataChanged
адресный, no reset при edits; TSV целиком валидируется до публикации. Snapshot writer всё
ещё выполняет full inventory/load/encode/delete+insert transaction. Числа before/after —
validation/iteration4-table-*.json; edit latency улучшена, save/reopen остаются узким местом.

Следующий контракт ARU-45/46/47/52: immutable ChangeSet(project generation,base revision,
new revision,entity IDs,table row/column/cell deltas), единственный writer, compare revision
в BEGIN IMMEDIATE, validate affected invariants, whole-operation commit/rollback; ordered
ACK ровно revision и адресный GUI refresh. Whole snapshot остаётся для initial load/backup,
никаких второго канона/ORM и прямого SQL в UI/domain. Нужны crash/retry/stale/draft/compound
checks и benchmark перед заявлением масштабируемости. Здесь incremental writer не реализован.

Backup4GiB остаётся синхронным и проверяет snapshot/assets/checksum; restore только в новую
папку, integrity/FK/UUID/version до публикации. G проверяет ENOSPC/повреждение/budget через
fault injection и новые объекты/MOW. Не выдавать такой тест за физическое заполнение диска
или фактический4GiB export. На NASA input29.7MB измерен GUI block≈0.94s, без tile cache.
ARU-54 остаётся открыта: worker над immutable online SQLite backup snapshot + frozen asset
inventory, bounded streaming hash/copy, progress и cancellation checkpoints, staging cleanup,
atomic rename только после integrity/checksum; disk-space preflight для TEMP и destination,
не перезаписывать restore target, не обрывать writer transaction. Политику больших объёмов
обосновать измерением, до этого предел не повышать. Background backup здесь только спроектирован.

Map: реальные NASA21600×10800,2окна/1000placements одной Card/30raster objects/2слоя на карту;
renderer, drag, import, reopen, save и backup измеряются раздельно. FullViewportUpdate остаётся
по результатам bounded repaint, без обещания SLA. Python/Qt/ADS/libvips версии не менялись.
Физические focus/float/мульти-DPI и чистая Windows без Python остаются ARU-63/64.
