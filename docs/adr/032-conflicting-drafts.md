# ADR-032 — явное разрешение конфликтных черновиков

Итерация7 F, ARU-46/78. Дефект воспроизведён до исправления отдельно в FieldEdits
и TablesService: A→B→conflictA→reopen/unchanged commit сохранял A поверх B.

Ошибочный ввод и конфликт — разные состояния. Conflict хранит raw, исходный base
и observed canonical value, независимо от времени жизни native editor owner.
Все последующие commit/blur/reopen/flush остаются неавторитетными до явного resolve.
Baseline ошибочного draft также переживает reopening: исправление синтаксиса
не обходит optimistic concurrency. «Использовать сохранённое» очищает draft и
устаревших владельцев без записи. «Применить мой вариант» проверяет observed value;
новое значение вызывает повторное разрешение. Парсинг и доменные инварианты сохраняются.
Сессия проекта владеет конфликтами; они не становятся частью SQLite snapshot.
Autosave/Ctrl+S сохраняют корректный канон и не блокируются соседним draft.

ConflictBar даёт оба действия в Card Editor, Inspector и общих TableWidget
(embedded/standalone); адресные уведомления по ID сохраняют active QTextDocument,
Undo, caret и семантические буферы. Отмена нового ввода восстанавливает прежний draft,
явный discard удаляет его; замена проекта очищает весь контекст.

Два воспроизводящих теста после исправления прошли. Целевой batch семантического
ввода, inventory, section lifecycle, drafts и resolution:21 passed на Windows QPA.


Дополнительно проверены оба направления embedded/standalone, invalid baseline,
third canonical edit, Save ACK, explicit UseSaved и entity picker expected-value conflict.
ConcurrentEditError переносит baseline/current в reject_draft, поэтому picker не обходит
conflict state. Metadata/draft notifications Card не hide/reinsert embedded Table;
rich section UUID notification, включая discard, продолжает синхронизировать документ.
Новый native reproducer сначала удалял активный QLineEdit при summary update,
после адресного body refresh сохраняет editor/raw и не делает ранний commit.
