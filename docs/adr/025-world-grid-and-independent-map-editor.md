# ADR-025 — world grid и отдельный Map Editor

Утверждённая итерация5 заменяет grid pass и встроенный edit mode ADR021. Владелец
отклонил встроенный интерфейс4: он не является целевым или принятым. Viewer и editor —
два ADS окна map:UUID / map-editor:UUID, одна Map Entity/ModuleSession/Undo/writer/tiles.
Камеры/selection каждого view независимы, сохраняются отдельно. Map deletion/project close
закрывают оба; повтор open editor фокусирует существующий. Режим-checkbox и длинное меню
редактирования viewer удалены. Editor: tools/layers/palette слева, canvas, inline transform
properties выделенного объекта справа; select/pan/place, Escape отменяет текущий drag.

Смещение воспроизведено на настоящем viewport.render при ненулевом target origin и DPR:
старый deviceTransform уже включал paint-engine offset, resetTransform сохранял engine
translation — offset применялся повторно. Теперь QPainter рисует world lines под текущей
матрицей ровно один раз, clip map rect в тех же world coords, zero-width cosmetic pen
один физический пиксель, AA только grid выключен. Никаких ручных постоянных компенсаций.
12live raster cases ×3pan/resize: known background bounds + known world line, zoom .73/
1.37/4 и DPR1/1.25/1.5/2. Старый код падал, новый проходит (27.13s). Это не ручная mixedDPI
приёмка. LOD только viewport lines, source tiles/libvips/footprint сохраняются.

MapGrid.snap/snap_point и UI/codec/calls удалены, токены свободны. Map payload5/SQLite12.
Palette использует bounded existing media decoder и visible48px previews с LRU128, native
worker source backgrounds не декодируются сюда. Raster objects/layers остаются отдельными
от Card/Token; delete layer с данными требует подтверждения. Vector roads/walls/fog/lighting/
combat/BigMap не реализуются. Результат native window/UI lifecycle и benchmark — отчёт5.

Итерация6-rev3 заменяет соответствующие границы владельцев, refs/semantic input, graphite composition и crop lifecycle: ADR-027/028/029. Исторические имена смешанных controllers/sessions выше больше не используются.
