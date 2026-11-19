# ADR-028 — ссылки, проекции и граница редактирования

Утверждённый пакет6-rev3 требует обычную дочернюю Table с четырьмя колонками, живыми
ссылками на item и независимым вводом в двух представлениях. Сигнал textEdited не является
semantic commit; broad Card refresh при изменении Table удалён в A.

Единственный формат SQLite13/Table3 (Card4/Map5 прежние). ColumnDefinition дополняется
стабильным key, entity_ref constraints kind/card_type, projection(source_column_id,
field_key) и простыми number constraints/default/required. Это не формульная DSL.
Проекции read-only, их значения не входят в rows/SQLite. Удалённый source descriptor
сохраняется с диагностикой. Target UUID soft reference: input проверяет доступность и
constraints, последующее удаление/смена типа сохраняет UUID/количество.

Inventory: item nullable Card(item), quantity integer>=1/default1, description_preview
(summary либо safe short description) и unit cost, None отображается «—»,0 остаётся0.
EntityQueries — ID/search index и immutable public ReferenceInfo, не второй канон.
Table reverse index адресует только строки, зависящие от изменённых targets. Picker —
model/view по title/aliases, path/UUID различают одноимённых. Object library использует
тот же каталог Card(object), но размещает оригинальный asset без portrait crop.

TSV ссылки — canonical UUID, без поиска/автосоздания по имени; projection range paste
отклоняется целиком, копирование содержит отображаемые проекции и UUID ссылок. Вставлять
обратно можно только writable range. Зависимые source columns не каскадируют строки.

Structured edit buffer владеет table/row/column UUID (или card/field), baseline и raw text;
локальный QLineEdit сохраняет курсор/Undo. Enter/Tab/blur подтверждают один полный ввод,
Escape отменяет, checkbox/picker дискретны, TSV атомарен. Explicit Ctrl+S/close/switch
flush валидные активные buffers; autosave иных данных не публикует незавершённое слово.
Сравнение baseline предотвращает silent overwrite другого представления; удалённая
ячейка сохраняет raw orphan draft для явного исправления/отбрасывания. Persist ACK не
меняет Qt editor. Нативные insert/remove/layout/persistent indexes сохраняют UUID editor
при reorder, а delegate не выполняет повторный setEditorData активного ввода.

Rich text — один непрерывный QTextDocument, публикация после250ms idle с max2s: это
coalescing дорогой сериализации/валидации, не исправление Table focus таймером. Explicit
flush перед switch/save/close, editor никогда не зависит от наличия фокуса для autosave.
UI обновляет header только при изменении его полей. Invalid drafts, pending input,
dirty/saving/ACK и I/O error различаются. Window не disabling ради Ctrl+S.

Схемы/проверки и измерения hot paths фиксируются после B–E. Legacy/migrations не нужны;
unsupported schema получает отказ без записи. Full snapshot/sync backup4GiB не переписаны.

Итог6: полный pytest394passed/1skip64.76s, после финальных local fixes targeted29passed3.66s (включая новый constraint regression) и22passed2.52s portrait/layout. Ruff/pip/diff clean. Actual imports83modules/174edges/0cycles; draw.io и JSON в docs/architecture. Подробные measurements/build/native limitations — единый отчёт6.
