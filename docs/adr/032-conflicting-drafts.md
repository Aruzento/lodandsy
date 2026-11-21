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

## Финальная стабилизация после приёмки итерации7

ARU-46/78, audit9e06c0b: B commit(finish=False), затем A conflict, cancel(B)
удалял чужой draftA. Начальный snapshot редактора больше не означает владение текущим
draft. FieldEdits и TablesService отмечают каждую публикацию новым session-only token;
owner хранит последний увиденный/опубликованный token. Cancel восстанавливает snapshot
только при совпадении token, иначе завершает лишь локального owner. Повторная публикация
того же raw и изменение observed/error тоже меняют token: сравнения строк недостаточно.
Snapshot включает error/base/conflict copy, поэтому Escape возвращает согласованный
статус; None остаётся настоящим baseline, а не признаком отсутствия. Явный resolve
удаляет stale owners, project reset очищает поколения. Persistence/UI формат не меняется.

Regression tests проверяют оба сервиса, finishFalse/True, flush, UseSaved/ApplyMine,
старый initial draft, third canonical edit и None baseline. Native Qt keyboard tests:
Ctrl+S→conflict→Escape→blur, Card и оба направления embedded/standalone Table;
сохранение оставляет канон B, draft A доступен до явного решения.

## Дополнение 21.11.2026 — ADR-033

FieldEdits принимает ValueAddress(card_id,field_id,actor_id optional), Actor contexts
изолированы от базы и других участников. Тот же optimistic/explicit resolve путь,
semantic commit/generation ownership. Удаление Actor retire только его адреса после
commit. Formula editor имеет локальные drafts и preview по rules revision+state serial;
Apply/Reset атомарны, preview не авторитетен после смены проекта/входов.


## Дополнение UI-приёмки — ADR-034

Новые формы используют тот же FieldEdits с явным ValueAddress и owner generation.
Переключение Actor завершает только ввод своего binding; чужой conflict draft не
переназначается и не перезаписывается. Системная page не создаёт RichDocument и не
меняет Undo обычных UUID секций. Item modifiers применяются явно, typed dialog
сохраняет UUID; отмена формы не пишет канон. Rules draft отдельно guarded preview.
