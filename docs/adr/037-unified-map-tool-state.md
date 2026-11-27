# ADR-037 — единый инструмент игровой карты

25.11.2026, ARU-91. M5 e40a25d принят владельцем82/82, включая clean Windows.
Новая панель требует собственной ручной приёмки. Git-публикация текущим заданием не разрешена.

MapView(viewer) owns один MapToolState с active, last_shape и временным Space-return.
Last shape — предпочтение экземпляра, не второй active. FogTools/VectorTools читают
производный режим и разрешение событий из state; видимость context widget ничего
не активирует. QAction checked/курсор/drag flags/context — проекции state.changed.
Player и принятый фоновый Map Editor не получают эту панель или игровой state.

Switch отменяет локальные fog/vector/token previews через прежние адаптеры. Space
отменяет незаконченный жест, временно включает pan и восстанавливает только режим;
release/focus loss не оставляют grab/cursor. Escape отменяет без изменения канона.
События V/H/B/E/M/Space обрабатываются только view/viewport, без global shortcuts,
не перехватывают текст в Inspector/context/Card Editor. Ctrl+Z/Y остаются прежним
Map Undo. Measure — параметры существующего token drag, не самостоятельная линейка;
он допускает выбор/перемещение токенов. Token tool размещает через прежний point picker.

После успешного service commit нового shape/portal state возвращается к select;
cancel/validation failure не выдают успех. Brush/eraser остаются активными. Порталы
доступны в select без открытия прежней панели. Все прежние geometry/validation,
public visibility/portrait/fog/measurement handlers и canonical save contracts сохранены.

Native vertical QToolBar из QAction с icon20/button36 и native overflow; shape menu
запоминает last_shape. Общая верхняя панель — Undo/Redo/grid/fit/settings/editor/player.
Grid — быстрый доступ к прежнему enabled, настройки открывают прежний grid/calibration
dialog. Context — только параметры active tool; object properties остаются в Inspector.
Нет новых domain entities/settings/schema/Undo stacks/framework/dependencies.
SQLite16/Card7/Map8/UIstate4 без изменений. Explicit ownership и matrix — validation report.

Контекст fog переносит группы параметров по ширине; selected token сохраняется при
смене режима, меняются movability/accepted buttons. Это UI-инварианты, не поля мира.
Финальная проверка и физическая приёмка: docs/validation/2026-11-25-map-m55.md.


## Уточнение после ручной приёмки, 26.11.2026

Финальная полировка заменяет measure-mode параметром существующего token drag
в диалоге сетки (D&D 5e 2014 / Геометрическое). Выбор/вершины — одна раскрывающаяся
группа, last_selection такое же UI-предпочтение как last_shape. V всегда выбирает
объекты. Native toolbar: icon18/stroke1.15, hit36; редактор справа с текстом.
Flyout имеет10 logical px gutter и ограничен availableGeometry текущего экрана.
Скрытие подписи портала и совместимость Map9 описаны в ADR-038.

## Inspector после фиксации v0.01, ARU-91

Контекстные виджеты Viewer размещаются в общем Inspector для активного окна
`map:UUID`. WindowManager публикует активацию через фокус и вкладки ADS. Viewer
создаёт и освобождает единственный набор контролов на карту, включая параметры
тумана, подсказки фигур и порталов. Режим и геометрия жестов остаются в MapToolState
и существующих адаптерах. Space временно сменяет контекст вместе с режимом.
В режиме выбора Inspector показывает фигуру, участника либо свойства портала.
Для выбранного токена доступен существующий режим измерения из окна «Сетка и
масштаб». Оба входа используют одну прикладную операцию и то же предпочтение.
Player и редактор фона остаются вне этого контекста. Форматы данных прежние.
