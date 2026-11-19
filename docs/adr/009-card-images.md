# ADR-009 — изображения в Markdown Cards

Принято 19.11.2026, ARU-73. Исходный Markdown остаётся каноническим; команда файла,
paste и drop используют один application service. Alt экранируется, ссылка имеет
вид `![Описание](assets/UUID.png)`. Просмотр не меняет source.

Вместо полного QImage в GUI используется один worker, thumbnail до 1024 px,
общий LRU 16 MiB/128 записей, очередь preview до 32 и бюджет документа 8 MiB.
Исходные raster PNG/JPEG/WebP/BMP/GIF проверяются по signature и декодированием:
до 64 MiB и 32 MP; SVG запрещён. Это профиль Card, прежний renderer Map не меняется.
При resize размер image format меняется только в производном preview document.
Недоступный, повреждённый или превышающий бюджет ресурс заменяется текстом.
Сетевые URI не передаются загрузчику. Path containment учитывает symlinks.

Публикация: UUID temp → fsync → rename → AssetRecord + Markdown через session →
общий save pipeline. Проверяются уже скопированные байты. Дедупликация SHA-256
переиспользует только ресурс с проверенным содержимым. Прерывание до SQLite commit
может оставить непривязанный immutable файл; ссылок на недописанные файлы нет.
Undo не удаляет ресурс, backup сохраняет его. Switch/close/save ждут импорта.
Clipboard кодируется PNG в worker; обычный текст вставляется без преобразования.

Проверено тестами: форматы, thumbnail bounds, insert/Undo/Redo, closed editor,
удалённая Card, duplicate, кириллица, save/reopen/move/backup, corrupt/missing,
remote/file traversal и paste. Проверка symlink пропущена, Windows account не имеет
прав на создание symlink; прежние path policy тесты проходят. Native paste/drop,
узкое окно и итоговый дистрибутив остаются в ручной приёмке. Пересмотр при требовании
гигантских иллюстраций: отдельный bounded decoder, а не увеличение лимита в GUI.
