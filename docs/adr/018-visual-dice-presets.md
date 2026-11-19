# ADR-018 — визуальные кубики и сохранённые заготовки

ARU-79. DiceDocument — Entity с UUID/title и модульным payloadv2: ordered presets
{UUID,name,config}. DiceConfig: семь целых количеств в порядке4/6/8/10/12/20/100 и
модификатор. В сумме≤1000, |modifier|≤1e9, zero config допустим для очистки, zero roll
отвергается. Один pure roller с внедряемым RNG, результаты по типам и итог вычисляет
домен. Обязательный строковый parser и expression-only формат/виджет удалены по правилу
владельца; человекочитаемая формула теперь только производное отображение конфигурации.

Сохранение — SQLite schema10, Dice payloadv2 JSON внутри канонической БД, общий writer.
Нет второй копии конфигурации в UI. Правки активной заготовки сразу публикуются по ID;
выбор — UI state. Бросок не изменяет preset/revision/dirty. Runtime history≤50, last/total
переживают close/reopen документа в сессии, не пишутся в проект/backup. Presets создаются,
дублируются с новым UUID, переименовываются, удаляются с подтверждением. Последний можно
удалить; новая заготовка доступна без искусственного восстановления удалённой записи.
Иконки SVG встроены, новых зависимостей нет. Unknown fields/version отклоняются без записи.

Проверки: mixed/negative/d100/RNG bounds/zero/limits, invalid name/duplicate ID,
create/rename/duplicate/delete-cancel, independent documents, clean roll/history bound,
save/reopen/backup/runtime reset. Ручные Windows скриншоты/DPI/поставка — G.
Не вводить rules engine/сохранённую историю без отдельного продуктового требования.
