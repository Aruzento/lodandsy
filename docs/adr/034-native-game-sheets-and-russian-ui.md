# ADR-034 — нативный игровой лист и русская граница представления

21.11.2026. Исправление непройденной ручной приёмки ARU-65/80/83 по пакету
LODANDSY_UI_acceptance_fix.zip. Baseline8f73f06/main и CI44912417146 проверены.
Новый запрос отменяет «характеристики только Inspector», не ADR-027/032/033.

Cards-owned виртуальные страницы `system:attributes` (Character/Creature/Object)
и `system:modifiers` (Item) существуют только в представлении. Они не Section,
не пишут rich text/значения в content, не меняют Card6/SQLite15 и не мигрируют мир.
UUID обычных вкладок, их порядок/редактирование, QTextDocument и Undo сохраняются.
UIstate4 допускает эти явно перечисленные active_section keys, старые UUID работают.

Игровой лист получает Card/ActorRef/effective queries через отдельный Cards binding,
переиспользует общий FieldEdits/ValueAddress/expected value, не новый edit manager.
Контекст по умолчанию — база; просмотр не создаёт Actor. Выбор участника явный,
переключение завершает только своих владельцев ввода. Actor читает общую базу,
пишет только индивидуальные state/overrides. Его inventory открывается по owned Table
ref, без подмены template inventory. Контекст окна не переназначает другой Inspector.

Inspector Card технический, остальные существующие типы сохраняют доступные поля.
Оперативный Actor/Map Inspector сохраняет state/scene behaviour. Gameplay editing
и Item modifiers принадлежат системным страницам. Матрица всех FieldDefinition
фиксируется в validation report. ID/choices/domain остаются каноническими; labels,
статусы, единицы и понятные ошибки переводятся только UI catalog.

Компактные native Qt controls: ресурсы сверху, 6/3/2 ability tiles с derived modifier,
явный base input; сгруппированные saves/skills/другие поля, история хитов по уровням,
раскрываемые источники. Один вертикальный scroll, высота по содержимому, без web runtime.
Item editor — список + typed dialog, закрытый searchable target catalog, UUID стабильны,
локальные drafts/явное Apply/Cancel и подтверждение удаления при применении.

Правила открываются из существующей шестерёнки и остаются одним окном текущего проекта.
Русские категории/поиск/typed examples, advanced safe formula syntax; preview — таблица,
явные Apply/Reset/Cancel, revision+serial+generation guards и предупреждение о HP clamp.
Закрытие несохранённого draft подтверждается, смена проекта закрывает stale window.
Ни вычислитель, ни форматы/игровые правила ради представления не изменяются.

Новых зависимостей нет. Новые helpers явно Cards-owned в architecture gate.
Полный gate/build после целевых блоков; source/frozen parity и новый ZIP/SHA.
Визуальные снимки и физические ограничения фиксируются отдельно. Ручная приёмка
не объявляется пройденной; Linear остаётся In Progress. Commit/push/merge запрещены
до нового разрешения, release не создаётся.


## Дополнение 22.11.2026 — ADR-035

Лист v2 и equipment facts заменяют сохранённую броню/щит Card и прежние proficiency
формы. Новый SQLite16/Card7/profile2 по прямому разрешению владельца «все миры тестовые»;
миграций/legacy нет, старые файлы отклоняются без записи. Actor/Token ownership,
FieldEdits, native document lifecycle и функциональные границы сохранены.
Generic Tables cell hooks собирает composition root; pure EquipmentFacts и профиль —
Cards. AST105modules/264edges/0cycles, gate не ослаблен. Подробности и критерии1–7:
docs/validation/2026-11-22-character-sheet-v2.md.
