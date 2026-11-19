# ADR-021 — тонкая сетка, слои и однонаправленный MOW reader

> Историческая запись: противоречащие итерации5 решения отменены. Текущий контракт — ADR-023…026 и docs/MVP.md.

Принято в границах утверждённого пакета4, ARU-77/81/82. Дорогое изменение renderer
не требуется: прежняя GridLayer рисовала полупрозрачную3px тень поверх1px линии, а dirty
rect мог менять antialias края. Убраны тень/двойной pass, линии выровнены по физическим
пикселям deviceTransform/DPR, AA отключён только у grid. FullViewportUpdate исключает
накопление alpha/швы частичной перерисовки. TileLayer и LRU сохраняются. Рассмотренный
foreground overlay менял бы порядок поверх токенов без необходимости; остаётся scene layer.
12 raster regression случаев подтверждают1px/repeatability на4zoom×3DPR; mixed DPI физически
не доказан этим тестом. Условие пересмотра — измеренное ухудшение repaint тяжёлой сцены.

MapLayer/PlacedAssetObject принадлежат Map payload4/SQLite11: JSON массивы слоёв/объектов
валидируются доменом, неизвестный kind/слой/геометрия/дубликаты отвергаются. Только raster,
не абстрактный будущий path editor. Порядок background < raster layers < grid < tokens;
layer.position непрерывен, z объекта локален слою, tokens всегда выше. Hidden сохраняет
данные, delete nonempty требует explicit flag + UI confirmation с числом объектов.
Редактор карты переключает hit-test/drag; move/resize/rotation/delete/visibility/order
идут через ModuleSession/тот же MapEdit Undo. Не копирует Card/assets. Валидационные лимиты
1000слоёв/10000объектов/10000tokens не обещают производительность этих пределов.

MOW: reader на stdlib HTMLParser + ограниченная грамматика YAML, вместо новой PyYAML
native/runtime зависимости или собственного полного YAML. Только плоские scalar/inline
lists, v1. Reject constructors/anchors/complex/deep headers; bounded bytes/files/nodes/depth.
Это явно заявленный subset, неподдерживаемое не угадывается. Чтение/prepare отделены от
GUI apply и выполняются в existing bounded module executor; проект не переключается
во время операции, закрытие ждёт завершения. UUID выделяются первым проходом, parent/order/
wiki links строятся вторым. Current Entity.atomic публикует весь forest либо ничего;
после commit единый writer делает SQLite transaction. Новый staged asset до DB не является
потерей целостности: ошибка удаляет только свои неподтверждённые файлы; process crash может
оставить безопасный orphan asset, который сохраняется backup, ссылок на отсутствующий файл нет.

Реальный приложенный файл: UUID заканчивается afc3-5c46560fcaf0 (в тексте задания af3c —
опечатка). Подтверждены folder/title/tags, пустые summary/body/portrait, missing parent.
Read-only просмотр MOW js/core/markdown.js, templates/cardShell.js и wiki/references.js
подтвердил card shell и .wiki-link[data-page-id], img[data-asset]. Прямой img src переносится
через safe containment и общий importer; data-asset без manifest диагностируется, не
превращается в выдуманный путь. Runtime controls/data-runtime/scripts/CSS исключаются,
результат проходит текущий whitelist. Unknown blocks сохраняют безопасный видимый фрагмент
с warning. Ни stat inference, ни MOW runtime/tables/combat/v2 variables не реализованы.
Повторный source UUID: skip по умолчанию или явный remap/newUUID, никогда overwrite.

Доказательства: реальные sample+синтетические linked/order/media/repeat/cycle/duplicate/
unsafe YAML/traversal/junction/rollback/save/backup тесты перечислены в отчёте4. Изучение
исходного кода не считается проверкой дополнительных реальных пользовательских документов.
Расширять subset только по реальным exports/manifest с новыми fixtures и бюджетами.
