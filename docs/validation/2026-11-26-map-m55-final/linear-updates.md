# Готовые обновления Linear — 26.11.2026

Запись через MCP недоступна (Unknown tool), UI helper не инициализируется (os error3).
Не публиковать дубли задач. Обе задачи остаются In Progress до приёмки владельца.

## ARU-91

Финальная полировка по всем9 замечаниям реализована: SVG18px/stroke1.15/hit36,
new-map feet5 без переписывания старых, измерения в диалоге сетки, measure buttons
удалены, editor единственный текстовый справа, screen-aware flyout gap10logical px,
select/vertices одной группой, тонкие разделители fog. MapToolState/Space/shortcuts/
auto-select/overflow сохранены.97 passed/1 skipped целевые; полные Windows564/1skip,
offscreen563/2skip. Ruff/pip/diff/architecture109modules276edges0cycles green.
Windows build и source/frozen parity111modules прошли. Реальные QWidget evidence
DPR1/1.25/1.5/2; инженерный отчёт docs/validation/2026-11-26-map-m55-final.md.
Новый кандидат `LODANDSY-Map-M5.5-Final-2026-11-26.zip`, SHA256 в sidecar.
Git-публикация не выполняется, новую ручную приёмку не объявляем пройденной.

## ARU-89

В нативном create/edit portal dialog добавлен «Не показывать название на карте».
label/UUID сохраняются; скрывается только caption, icon/double-click/navigation/
Player follow прежние. hide_label strict bool в Map9, читает7/8 без записи с default
false. SQLite16/Card7 прежние, старый max8 writer откажет9 вместо потери поля.
Cancel/Undo/Redo/typed validation/pixel paint/Player exclusion/Map8 no rewrite/
Map9 reopen/backup проходят. ADR-038 фиксирует узкую совместимость. Поставка общая
с ARU-91, прежняя приёмка M5 сохраняется; новая checkbox-полировка ждёт приёмки.


Итог поставки: source/frozen/fresh Unicode portable smoke с NASA233MP passed.
Windows-only PATH, Python/Qt env очищены, EXE/report SHA binding сохранён.
Все128 binaries совпадают с проверенным portable;152 реальных Qt PNG. Внешний
блокер записи Linear сохраняется. Commit/push/merge не выполнялись.
