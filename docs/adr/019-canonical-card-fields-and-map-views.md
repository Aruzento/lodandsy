# ADR-019 — поля канона и представления карты, итерация 4

Утверждённый пакет A–G от19.11.2026, ARU-80/65/77/81/82. Инженерное решение в его
границах: сохраняем Core Entity forest, Qt ADS и S3. Заменяет data/layout части
ADR-010/014/015/016, не меняет безопасный Qt HTML, writer и libvips ADR-011.

CardTypeDefinition определяет смысл и поддержанные поля; TemplateDefinition — компоновку
SectionDefinition. Смена шаблона не меняет тип и значения. Базовые определения встроены,
пользовательского schema builder нет. FieldDefinition задаёт стабильный ключ, тип,
default/unset, группу и ограничения. Immutable values — scalar/tuple text list/UUID;
Qt HTML только для richtext. Entity.title единственный title, доступ name — его проекция.
Описание хранится единожды в Card.content и доступно по description; другие richtext
области — по ключам. Портрет — один Portrait asset reference/alt/caption. Summary/tags/
aliases/HP и другие характеристики не извлекаются из HTML. Optional featured — нейтральное
bool поле метаданных, без игровых правил. None/отсутствие/0/false/пустой текст различимы.
Все изменения через ApplicationSession с адресными ключами; валидация целого изменения
до публикации. Inspector/Card/Search читают одну модель. Не создаём отдельный канон HP.

Card payloadv3: card_type/template_id/fields + document Qt HTMLv1 + portrait.
SQLite11 — только текущий контракт, промежуточные тестовые миры пересоздаются; старые
версии отклоняются без записи. JSON fields строго валидируются, unknown/duplicate keys
не игнорируются. S3 revision/транзакции/backup остаются общими.

Последовательные C/E расширяют Map payloadv4: TokenInstance обязателен card_id и хранит
только local position/footprint/z/layer и явно nullable presentation overrides. Имя/HP/
portrait/default kind читаются из Card, не копируются на карту. Удаление Card атомарно
удаляет её размещения с предварительным предупреждением. Неожиданный broken ref —
диагностика, не автосоздание Card. Undo не восстанавливает чужой канон.
MapLayer и PlacedAssetObject(UUID/layer/asset/rect/rotation/z,kind=raster) независимы
от TokenInstance, фон — tiles, grid — отдельный scene layer с полным viewport repaint, camera/selection — UI.
Слой с объектами нельзя удалить молча; hidden сохраняет данные. Дальнейшие geometry
kinds добавят payload, а не новую таблицу на каждый вид объекта.

F: MOW parser/staging отдельно от apply. Два прохода UUID mapping, явный skip/remap,
source UUID/type сохраняются как typed metadata; это внешний импорт, не legacy runtime.
Источник read-only, runtime HTML исключается, media только внутри выбранного корня,
применение транзакционное с rollback и общим save path. Реальный MOW пример и fixtures
различаются в отчёте; полнота форматов подтверждается кодом/образцами, а не описанием.

Пределы: нет Ruleset/eval/combat/Campaign overlays/web runtime/ORM/SDK. Проверки,
измерения и возможные отклонения фиксируются в едином отчёте итерации4 после G.
