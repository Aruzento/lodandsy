# ADR-024 — native shell, portrait crop, итерация5

Владелец отклонил внешний вид4. Визуальный контракт docs/design/iteration-5-layout.md
заменяет body forms/templates/tags/aliases и служебную полосу portrait. Qt Widgets/ADS
сохраняются. FixedPanelHost теперь fixed-position QDockWidget с native QMainWindow
separator, не QToolBar фиксированной ширины; sidebars не участвуют в ADS. Width/visibility
отдельно в UIstate4, restoreGeometry/saveState и explicit remembered widths при collapse.

Portrait asset+normalized crop — единственный контракт. Неизменяемый ориентированный
источник декодируется существующим bounded QImageReader с EXIF auto transform. Crop dialog
показывает рамку3:4/затемнение/drag/zoom/preview/keyboard, Apply/Cancel/Reset. Применение
меняет только normalized rect, не файлы и не screenshot. Replace сбрасывает crop. Panel
240–280logicalpx wide, adaptive height, empty clickable, hover/focus replace/crop/remove;
доступные имена фиксированы, caption/alt UI/data удалены. Token presentation наследует
тот же rect только при использовании portrait; собственный token_image/instance override
не обрезается чужим crop. Character circle и item alpha/aspect fit сохраняются.

Ручной screenshot и mixed DPI обязательны как приёмка, synthetic Qt render tests —
только проверка геометрии/пикселей. Результаты и ограничения фиксируются в отчёте5.
