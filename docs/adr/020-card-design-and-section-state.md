# ADR-020 — Qt Card design contract и состояние разделов

ARU-26/75/76/33, утверждённый B итерации4. Семантические цвета/состояния существующей
Fusion темы, Segoe UI, шаг8/16/20, gold focus, минимум декоративных границ. Hero title22px,
summary14px, content наследует форматирование документа. Совместные style tokens применяются
к Tree/Inspector/Card, остальные модули сохраняются. Motion не нужен для частых правок.

Header: единственное значение title, отдельные type/template, summary/tags/aliases и
портрет до220×196px. Alt/caption — контекстный диалог, вместо нескольких полноширинных
строк. При ширине<640px portrait выше metadata; ограниченный header scroll сохраняет
место редактору. Поля типа раскрываются группой, Inspector использует тот же Field API.
Toolbar показывает основные действия, остальные/шрифт/цвет/масштаб — видимое меню «Формат»;
hotkeys сохранены, overflow Qt работает в узком окне. Это native Qt, не CSS/web runtime.

Каждая richtext область хранится один раз по ключу. Один RichDocument на Card/section в
сессии, один активный QTextEdit. Переключение раздела/окон сохраняет native Undo, выделение,
курсор, scroll/scale; изменения в неоткрытом разделе не подменяют текущий. Layout template
не копирует richtext в HTML и не меняет Card type. Invalid typed drafts — session state
по Card ID/field key, общие для представлений; видны, переживают закрытие редактора и
блокируют snapshot, пока не исправлены/явно отменены. Canon не принимает частичные правки.

Применены better-ui/layout/typography в пределах Qt и существующей плотности. Reference
current-card.png — проблемный снимок владельца, не целевой макет. Native screenshot/DPI
проверяются в G при доступном capture, синтетические иллюстрации их не заменяют.
