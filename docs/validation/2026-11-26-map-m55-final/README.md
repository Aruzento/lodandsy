# Реальные снимки финальной панели M5.5

Windows production Qt widgets, QWidget.grab, одноразовый синтетический мир; без личных вложений.
Снимки не подменяют физическую приёмку mixed DPI, второго монитора или чистой Windows.

|DPR|Панель|Сетка и измерения|Портал|Узкий fog|Меню фигур|
|---|---|---|---|---|---|
|1|[Панель](scale-1/24-m55-unified-wide.png)|[Настройки](scale-1/25-m55-grid-measurement.png)|[Чекбокс](scale-1/36-m55-portal-hide-label-dialog.png)|[320×300](scale-1/32-m55-narrow-fog.png)|[Шесть форм](scale-1/28-m55-shape-menu.png)|
|1.25|[Панель](scale-1.25/24-m55-unified-wide.png)|[Настройки](scale-1.25/25-m55-grid-measurement.png)|[Чекбокс](scale-1.25/36-m55-portal-hide-label-dialog.png)|[320×300](scale-1.25/32-m55-narrow-fog.png)|[Шесть форм](scale-1.25/28-m55-shape-menu.png)|
|1.5|[Панель](scale-1.5/24-m55-unified-wide.png)|[Настройки](scale-1.5/25-m55-grid-measurement.png)|[Чекбокс](scale-1.5/36-m55-portal-hide-label-dialog.png)|[320×300](scale-1.5/32-m55-narrow-fog.png)|[Шесть форм](scale-1.5/28-m55-shape-menu.png)|
|2|[Панель](scale-2/24-m55-unified-wide.png)|[Настройки](scale-2/25-m55-grid-measurement.png)|[Чекбокс](scale-2/36-m55-portal-hide-label-dialog.png)|[320×300](scale-2/32-m55-narrow-fog.png)|[Шесть форм](scale-2/28-m55-shape-menu.png)|

35 — меню выбора/вершин; 37 — скрытая подпись при сохранённой иконке; 30/31 — native overflow.
18/20/22 — безопасность Player, публичные фигуры поверх fog и original-image presentation.
34/35 снимки главного QWidget не включают отдельную native popup-поверхность. Само меню
видно на28, а gutter10 logical px и положение у границы экрана проверены UI-тестом.

Всего PNG: 152. evidence.json каждого DPR содержит фактическую платформу и масштаб.
