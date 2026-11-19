# ADR-017 — типизированные таблицы и нормализованное хранение

Итерация4: актуальные payload/поля/шаблоны/размещения/кеши — ADR-019…022. Противоречащие части этой записи являются историей; безопасный Qt HTML, S3 и текущий стек сохраняются.
ARU-78, итерация3. Минимальный контракт: ColumnDefinition(UUID/name/type/position),
RowRecord(UUID/position), immutable cells(column_id, scalar). Типы text/number/bool,
None отдельно от пустого текста;0/false участвуют в выборе целой записи. Домен валидирует
IDs/order/types, frontend использует QAbstractTableModel/QTableView без виджетов на ячейку.

Сравнили versioned JSON payload и нормализованные SQLite table_document/column/row/cell.
Измерение5000×20=100000cells: JSON encode0.125s/parse0.044s/5.56MB (без доменной проверки);
нормализованный общий writer save1.074s/load+validation0.817s/28.59MB. View0.479s,
single edit0.047s. JSON компактнее; нормализованный вариант принят из предложенного
пакетом предпочтения ради FK ячеек к строкам/колонкам и будущих индексов. Один canonical
формат, не SQL-таблица на каждый документ, без ORM/SQL-конструктора/формул. SQLite schema9,
Table payloadv2. Предметный модуль без SQL/Qt, транзакции общего writer сохранены.

Изменение типа строго проверяет имеющиеся значения: несовместимое изменение отвергается,
не преобразует/не отбрасывает данные. Непустое удаление требует подтверждения. TSV сначала
полностью валидируется, затем публикуется одним изменением. Активный валидный ввод идёт
в сессию сразу; invalid draft остаётся по row/column ID, виден и переживает close/reopen
в сессии, блокирует snapshot до исправления/явной отмены. Draft не является saved world.
Widths/selection — UI state по UUID, порядок строк/колонок — домен. Старые tuple[str],
QTableWidget и миграции удалены по решению владельца. Проверки типов/FK/random/копирования/
TSV/активного Ctrl+S/confirm-cancel/ID/restart/backup; ручная Windows/DPI приёмка в G.
Пересмотр при измеренной необходимости lazy loading/partial writer, не заранее.
