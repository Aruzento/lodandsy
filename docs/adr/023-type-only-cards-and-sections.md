# ADR-023 — type-only Card и UUID-разделы (итерация5)

Утверждённый пакет5 отменяет независимые templates/tags и фиксированные rich field keys
ADR019/020. Единственный выбор CardTypeDefinition задаёт начальные CardSection и подходящие
поля. Смена типа сохраняет введённые sections/values. Typed характеристики только Inspector;
aliases остаются в source data/resolver, без UI. Add field — отдельная application операция,
проверяет допустимость/отсутствие до изменения; повтор никогда не reset.

SQLite12/Cardv4. CardSection: UUID/title/position/kind rich_text|table_ref; rich content либо
Table UUID, без копии таблицы. Необязательный built-in purpose description/inventory — intent
при создании, не storage key и не отображаемое имя. Primary content — только read-only
проекция description section; удобный constructor content преобразуется в этот же раздел,
одновременные content+sections запрещены. Ни параллельных legacy форматов, ни миграторов.
Rich bytes≤2MiB/section,≤4MiB/Card,≤64sections; strict kinds/UUID/order/version.

Rich documents/Undo/cursor/scroll кешируются по UUID независимо от имени/порядка, tab state —
UI state. Инвентарь — ленивый table_ref: только явное действие создаёт одну дочернюю Table
с Предмет/Количество/Описание. Entity creation + Card reference публикуются одним Entity.atomic,
далее обычный revisioned SQLite transaction. Повтор возвращает ту же Table; отсутствие/перенос
цели диагностируется. Delete tab удаляет лишь ссылку/свой текст. Независимые/embedded Table
views используют ModuleSession и общий draft dictionary, адресные notifications без копий.

Portrait — явный единственный media contract asset+нормализованный crop (C), не мёртвая
ветка FieldDefinition. Metadata alt/caption удалены. Source assets неизменяемы; unsafe URI/
resources остаются запрещены. Результаты targeted/native/backup — в отчёте5.

Дополнено ADR-033: scopes/Actors/relations/HPmax, Card6; immutable type сохраняется.
