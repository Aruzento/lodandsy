# ADR-015 — структурированный портрет Card

Итерация4: актуальные payload/поля/шаблоны/размещения/кеши — ADR-019…022. Противоречащие части этой записи являются историей; безопасный Qt HTML, S3 и текущий стек сохраняются.
Принято в рамках ARU-76/утверждённого ADR-014. Портрет — optional typed Portrait
{asset_id, alt, caption} в Card payload v2, не HTML-разметка и не первая inline-картинка.
Отдельный QWidget отображает aspect-fit bounded thumbnail общего CardImages; ни текст,
ни Undo документа не меняются при загрузке/масштабе/смене портрета. Правки идут через
ApplicationSession и общий save pipeline. Персонаж остаётся Card, шаблон создаёт пустой
блок, другие шаблоны могут добавить его явной командой. Caption/alt — plain text.

Сравнение: inline guessing неоднозначен, новая RPG entity не нужна. Явное поле уже
предусмотрено утверждённым форматом. Shared immutable assets остаются после удаления
ссылки; отсутствующий asset сохраняет ID и placeholder, не вызывает filesystem fallback.
Импорт использует тот же bounded worker/публикацию, что body images и map tokens.
Legacy/migration не реализуются по последнему правилу владельца. Проверки: typed codec,
choose/replace/remove, independent inline, closed/deleted editor, save/reopen/backup,
missing resource. Ручная DPI/Windows приёмка — G. Пересмотр при новом типе media.
