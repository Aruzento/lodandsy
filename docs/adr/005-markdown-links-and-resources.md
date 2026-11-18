# ADR-005: Markdown, навигация и ресурсы

Статус: контракт подтверждён владельцем 18.11.2026; реализация и security cases проверены
автоматически. Сквозные функциональные сценарии полной Windows-сборки приняты владельцем;
это не ручное повторение каждого security case. ARU-59/60, ARU-33/58.

Выбран E2: QPlainTextEdit source и отдельный производный QTextBrowser preview,
source/preview/split. Preview никогда не сериализуется обратно в source. QTextDocument
source сохраняет Undo/Redo; режим и scroll — локальное состояние сессии по документу.
QTextBrowser — Qt Widgets, web runtime и другой renderer не вводятся.

Публичный синтаксис: `[Название](lodandsy://card/UUID)`. UUID разрешается исключительно
в текущем проекте. Label — независимый текст пользователя, rename Card не меняет
Markdown. Переход проходит через application layer, открывает/фокусирует документ по
ID и оставляет исходный редактор открытым. Unknown kind, неверный UUID и удалённая
цель дают сообщение и диагностику в preview, не передаются ОС. Копирование ссылки
из Tree или редактора экранирует Markdown punctuation в заголовке; используется ID
контекстной карточки, а не случайно выбранной другой строки Tree.

HTTP/HTTPS передаются QDesktopServices только из обработчика явной активации ссылки,
без дополнительного подтверждения, как разрешил владелец. Прочие схемы, включая
file/javascript/data/ftp, блокируются. Preview автоматически не загружает сеть.

Изображения разрешены только по относительному assets/... текущего проекта. Запрещены
absolute/UNC/file://, '..', encoded traversal, backslash/drive paths и выход через
symlink за assets. Локальное изображение проверяется QImageReader, общий бюджет
декодированных изображений на preview — 64 млн пикселей. Допускаются только raster
PNG/JPEG/BMP/GIF/WebP по фактическому формату; SVG не декодируется даже при расширении
png, чтобы исключить вложенные внешние ресурсы. Удалённые/недоступные
изображения заменяются текстом в производном документе. HTML img нормализуется только
для preview вне code examples, source не меняется. Неподдерживаемый HTML не исполняется.

Проверка обнаружила, что возвращать None из resource loader недостаточно: Qt может
использовать встроенное чтение file://. Поэтому PreviewDocument возвращает валидный
прозрачный sentinel для заблокированного изображения, а затем renderer показывает
текст. Другие ресурсы получают валидный пустой по смыслу byte sentinel. Вызов родительского
loadResource не выполняется. Новый производный QTextDocument создаётся при render,
кеш изображений не переносится между проектами. Регрессия проверяет настоящий
QTextDocument.resource для файла вне assets, а не только наш path helper.

Доказательства: tests/test_markdown_workflow.py проверяет source/Undo, переходы,
rename/delete, copy escaping, HTTP activation, опасные схемы, путь ресурсов,
native fallback, HTML images/styles и смену project root. Ctrl+F ищет по title/content
без SQL в UI и открывает отдельный документ. Размеры/производительность больших
Markdown с множеством картинок ещё требуют измерения; Qt Markdown не обещает полный
браузерный HTML/CSS. Пересмотр при смене renderer или публичного URI-контракта.

Первичный источник поведения ресурсов:
[QTextDocument resource/loadResource](https://doc.qt.io/qt-6.11/qtextdocument.html#resource).
