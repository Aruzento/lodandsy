# ADR-026 — Table, tool:dice и подтверждение сохранения

Утверждённая итерация5 отменяет random table mode, Dice Entity/presets и global draft gate.
ADR-019/020/022 остаются историей в соответствующей части.

TableDocument/TableWidget универсальны. Append-кнопки QHeaderView не входят в TableModel;
header drag переводится в единственный UUID-порядок. Встроенные table_ref и отдельные
окна используют тот же ModuleSession, адресные dataChanged и общий draft dictionary.
Не вводятся второй Table payload/инвентарная модель.

DiceConfig/roll_dice независимы от Entity/SQL. WindowManager держит singleton tool:dice;
ModuleController хранит config/results/history≤50 как сессию, переживающую смену проекта.
DiceDocument/DicePreset/payload/SQLite table удалены без адаптеров.

SaveCoordinator сохраняет валидный канон; invalid drafts не увеличивают revision и не
являются I/O error. Статус сообщает о них отдельно. Закрытие/смена проекта: исправить/
отбросить/отмена, сначала сохранить валидные изменения. RichDocument.pending_content —
transient undoable UI draft; canonical_content меняется после ApplicationSession ACK.
Sync использует ACK candidate без повторной сериализации всех больших документов.

Единственный формат SQLite12/Card4/Map5/Table2, UI state4. Старые версии отвергаются без
записи. Full snapshot writer, sync backup4GiB и assets protocol сохранены. Incremental SQL/
lazy load/background backup эта UX-итерация не реализует.

Доказательства: domain/session/UI/storage/MOW/20-images, frozen сценарии, таблица100k,
NASA233MP — validation/2026-11-19-iteration-5.md. Физическая mixedDPI/визуальная приёмка и
Windows без Python отдельно. Пересмотр при durable UI drafts, конкурентной записи или
фоновой операции backup.

Итерация6-rev3 заменяет соответствующие границы владельцев, refs/semantic input, graphite composition и crop lifecycle: ADR-027/028/029. Исторические имена смешанных controllers/sessions выше больше не используются.
