# Итерация5 — общий визуальный контракт Qt Widgets

Один native desktop shell: #0b111a фон, #121c29 рабочие поверхности, #263447 разделители,
текст #e8edf4, вторичный #aab7ca, сдержанное золото #ceb075 только выделение/primary action.
Segoe UI 10–11pt controls/12pt document, title20–22pt; плотность4/8/12/16/24 logical px.
Нет карточек внутри карточек, полноширинных полос одинаковых кнопок, рамок для декора.
Фокус виден; все icon actions имеют tooltip/accessible name, локальные shortcuts.

Shell: rail | resizable Tree | Qt ADS documents | resizable contextual Inspector | rail.
Границы панелей draggable QMainWindow separators; remembered width и hide/collapse отдельно.

Card: [название + copy link]          [портрет240–280×320–360]
      [тип] [summary2–3строки]       [hover/focus replace/crop/remove]
      [вкладки UUID …] [+]
      [компактный format toolbar] / [полноценная embedded Table]
      [свободный документ + локальная ошибка/draft]
Узкий dock: портрет уменьшается/ограничивается по высоте, минимум chrome; текст остаётся
главным. Ни template/tags/aliases, ни характеристик в body. Портрет empty clickable.

Map Viewer: [token+] [grid] [fit] [editor] [undo↶ redo↷] → canvas, никаких layer controls.
Map Editor (другое ADS окно): tools/layers/assets | общий tile canvas | selected object props.
Selection/pan/place явны; transform handles/inline properties, Escape отменяет жест.

Table: data headers … [+] по горизонтали; row numbers … [+] по вертикали. Нативный grid,
контекстные menus headers, selection/TSV как данные. Нет pseudo cells/random result bar.

Dice: приложение Инструменты→Кубики, один tool:dice; adaptive grid2–4columns счётчиков,
[формула + модификатор] [Бросить] [Повтор] [Очистить], заметный итог/детали/сессионная история.
Нет entities/presets/CRUD. Палитра/иконки/отступы одинаковы с Cards/Map/Table.

Проверки: native viewport/crop/resize/dock+keyboard на доступной Windows; снимки только
реального окна, недоступный capture не заменять синтетическим макетом/Qt.render.
