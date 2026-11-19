# ADR-008: команды Markdown и типографика просмотра

Статус: реализация ARU-72 в согласованном E2, без смены формата Card.

Панель могла бы применять QTextCharFormat/WYSIWYG и затем сериализовать документ,
но это меняет source и не выражает произвольные шрифты в Markdown. Выбраны явные
операции над текстом: pure application markdown_commands возвращает один диапазон
замены и выделение в UTF-16 координатах QTextCursor. Проверяются границы Unicode,
направление выделения, окружающий текст и однозначное снятие простых маркеров.

Inline-команды применяются к выделению или текущему абзацу; многострочные выделения
обрабатываются по непустым строкам. H1–H3, quote/lists/fenced code — по абзацам;
выделение до начала следующего абзаца его не захватывает. Разделитель вставляется
после абзаца, не удаляет выделение. Для embedded backticks выбирается более длинная
граница. Команды не являются полным CommonMark AST-редактором; сложный source остаётся
непосредственно редактируемым, Undo возвращает исходный текст.

UI применяет замену к прежнему QTextDocument внутри одного edit block, сохраняет
курсоры/scroll и историю документа. Действия и shortcuts принадлежат конкретному
Card Editor, в Preview недоступны с пояснением. Ctrl+B/I, Ctrl+Shift+X/Q/7/8/E,
Ctrl+E/K, Ctrl+Alt+0–3; Ctrl +/- и Ctrl+wheel управляют масштабом просмотра.
Image action добавляется следующим блоком ARU-73 вместе с реальным импортом.

Sans/serif/mono (Segoe UI/Georgia/Consolas) и масштаб 75–200% — только UI state.
Source показывается моноширинным шрифтом, preview — выбранным пресетом. Новый derived
QTextDocument получает font/style заново при render. Нет remote fonts/CSS/resources,
HTML-вставок в canonical content или toMarkdown serialization.

Настройки сохраняются и для закрытых Cards: UI DTO хранится лениво до открытия,
не создаёт заранее QTextDocument всех посещённых карточек. Прежний UI state читается
с defaults. SQLite schema и payload не меняются, UI preferences не увеличивают world
revision. При смене проекта preferences сбрасываются/восстанавливаются по проекту.

Доказательства: test_markdown_commands.py и прежние source/preview/security/lifecycle
регрессии. Проверены кириллица/emoji, reverse/multiline selections, no-selection,
toggle/Undo/Redo, keyboard scoping, link escaping/blocked URI, view-only prefs и reopen
закрытой Card. Native focus/DPI и читаемость проверяются при итоговой Windows-приёмке.
Пересмотр: только при отдельно согласованном WYSIWYG/посимвольных шрифтах или новом
публичном формате; текущие пользовательские Markdown-проекты не мигрируют.
