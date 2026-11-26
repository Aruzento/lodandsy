# ADR-033 — участники, переменные и правила 5e 2014

Продуктовый контракт утверждён владельцем 21.11.2026 в пакете
LODANDSY_5e14_Codex_package.zip, 01_REQUIREMENTS R01–R10. Реализация и доказательства
отслеживаются отдельно: docs/validation/2026-11-21-cards-actors-5e14.md.
Baseline main751b699, Windows CI44810679827 success. Этот ADR отменяет предложения
аудита о shared copy NPC, unset abilities, current выше max, отложенных формулах
и индивидуальном inventory. Номер 033 свободен на baseline.

Cards владеет immutable ActorState в CardPayload; Actor не Entity и не mutable
registry. ActorRef(card_id,actor_id), UUID глобально уникален, исходная Card неизменна.
Character/Creature/Object поддерживают участников; прочие токены остаются Card-only.
EntityCollection хранит opaque immutable project settings; конкретные rules принадлежат
Cards, Core не содержит D&D. ProjectActions объединяет Cards/Tables/Maps, pure validator
document_payloads проверяет итог внешней atomic операции до событий. Actor inventory —
обычная Table с отдельными UUID rows/columns; base inventory копируется один раз,
Item UUID остаётся ссылкой. Активность строки явная, default false; quantity не множит
модификатор. Удаление placement/map/layer сохраняет Actor/inventory; удаление Actor/Card
подтверждаемое и транзакционное. Player toggle выбирает existing/new, не переписывает
старые refs. NPC copy создаёт нового Actor с template inventory и initial effective HP;
Player copy использует основной Actor. Межкартовый перенос отложен.

FieldDefinition расширяется scope/applicability/nullable/default/binding/unit/derived;
одна политика constructor/update/replace/decode. hp удаляется без alias; hp_max integer,
hp_current/hp_temp Actor-only. Scores default10; технический предел1e9, без игровых
20/30. Derived не сохраняются. Manual HP/AC/speed — итоговый override включая bonuses;
auto рассчитывается отдельно с диагностикой. Inputs update→effective recompute→current
clamp при известном снижении max→validation→один in-memory commit. Рост не лечит;
null current не заполняется позднее. Load никогда не исправляет current молча.

Формулы: собственная интерпретация ast.parse(mode=eval), без eval/exec/compile.
Разрешены finite numeric/bool literals, имена, + - * /, unary +/-/not, comparisons,
and/or, условное выражение, floor/ceil/min/max и профильные pure функции.
Запрещены attributes/indexing/import/lambda/comprehensions/power/dynamic calls.
Лимиты:4096 UTF-8 bytes,256 AST nodes, depth32,4096 evaluation steps, magnitude1e9;
строгие типы, bool не number. Зависимости по stage IDs (base_*→effective→modifier→
dependent), DAG/cycle path до activation; unknown/error/unsupported отличны от0.
Project rules: stable dnd_5e_2014/version1 + immutable overrides/revision. Shipped
defaults не изменяются. Отдельный native editor: draft/test/preview/expected revision/
apply/reset; apply всего набора и обязательных clamps атомарен.

5e14 coverage: scores/modifiers, level/XP, proficiency1–20, initiative, saves,18skills/
expertise/passive Perception, явно заданные casting/weapon scalar inputs, armor bases/
shield, speed ft, carrying. HP — сохранённая история hit gains, первый die полностью,
дальше fixed/rolled input; недостаточная/неподдержанная история даёт unknown/unsupported.
Не реализуются combat, расход/отдых, spell/effect engine, attunement/слоты предметов,
другие rulesets и custom-variable constructor. Официальный источник SRD5.1 CC BY4.0:
https://media.wizards.com/2023/downloads/dnd/SRD_CC_v5.1.pdf; атрибуция в THIRD-PARTY.

Modifiers имеют UUID,target,operation,operand,stacking group/policy,priority.
Стадии set→multiply→add→minimum→maximum; конфликт равноприоритетных set диагностируется.
Не deduplicate по Item UUID: source=(actor,table,row,modifier); stacking policy
явная. Unsupported conditions дают диагностику, активность подтверждает ведущий.

Хранение: один snapshot/writer, новая SQLite15/Card6/Map7/Actor1/Rules1; actor/default/
tokens нормализованы, composite FK(card_id,actor_id), inventory FK/unique ownership;
state/tokens не дублируются JSON. UIstate4/Table3 сохраняются при неизменных descriptors.
Schema14 и старые payload отклоняются без записи/миграции; backup/restore сохраняют
UUID, rules/manual/activation. In-memory commit отличается от durable revision ACK.

History остаётся per-map, placement deltas и только изменённые компоненты.
Guard до QUndoStack index change; creation inverse запрещён при последующих правках
Actor/inventory/новых refs. Обычный delete token сохраняет state. Scalar/deletion Undo
не заявляются. Независимые HP/rules/inventory не входят в move/copy inverse.

Inspector context отделён от Tree/window; Card=base, token=Actor effective/state,
Item=modifiers; «Связи» показывает всех Actor, в том числе без размещений.
FieldEdits переиспользуется с адресом owner, сохраняет semantic commits и ownership
draft tokens. Actor events адресные, не broad Card/scene reset. Player/fog fail-closed,
Card Editor layout/QTextDocument/UUID sections и generation guards неизменны.

Все runtime helpers получают явного владельца в существующем architecture gate.
Новых production dependencies, EventBus/locator/ORM/второго writer нет.
Commit/push/merge разрешены владельцем только после доработки и проверок; release
не разрешён. Физические Windows/clean-machine проверки не заменяются pytest.

## Уточнения реализации и стоимость

Descriptor хранит scope/nullable/unit/choices/origin; binding title/description и группы
Inspector остаются в существующих контрактах. Derived catalog/profile отделён от
сохраняемых FieldDefinitions, новых пользовательских определений нет. read_value
различает absent/default/null/0/false; неизвестный ключ/неприменимый scope отвергается.
Переименование label не меняет ID; переименование/удаление системного ID — новая версия
формата. Existing alias name→title сохраняется, alias hp отсутствует.

ProjectActions injects CardsService.create_inventory(card_id,name); TablesService
клонирует один раз с remap row/column IDs. Fundamental five inventory columns проверяются
для owned inventory. Пропавший общий template даёт incomplete, сохраняется возможность
relink стандартного раздела. Независимые state edits не пишут Card field projections.
Item→Actor dependencies сейчас чисто пересчитываются на outer transaction, bounded
result cache≤2048 и compiled rules≤32; адресные events только при изменении результата.
Это линейный полный обход участников, не incremental dependency engine; замеры T27
показывают стоимость. Validation proof — один atomic tuple immutable inputs+max, compare
signature при каждом использовании; writer/GUI не могут смешать key от одной ревизии
с max другой. Proof/cache не сериализуются, load проверяет агрегат заново.

Modifiers≤4096 активных источников (плюс один встроенный shield); missing Item даёт
incomplete с diagnostic. Активность не подтверждает unsupported condition автоматически.
Source provenance содержит table/row/modifier UUID и имя Item, dependencies распространяются
на результаты. Две строки решаются explicit group/policy, не скрытым dedup по Item UUID.

Auto HP single-class: история gains имеет ровно level записей, первая равна hit_die,
каждая в пределах1..die. Если gain+CON<1, вывод unsupported вместо неточной трактовки
ретроактивного minimum; multiclass также unsupported. Unknown class/history не подменяется
формулой level+CON. Слоты и remaining Hit Dice не представлены пустым рабочим UI.
Carrying — STR×15lb только Small/Medium; CR proficiency manual, прочие размеры/class
features/penalties/exceptions/условия/attunement не автоматизированы. GM выбирает manual
или явно меняет поддерживаемую формулу. Profile допускает level>20 как данные, standard
proficiency выдаёт unsupported. Homebrew scores≥0 до1e9 без игровых максимумов.

API: create_actor→ActorRef; get_actor/list_actors; read_value(ValueAddress),
read_effective(ActorRef,field_id), update_values(owner,patch,expected_values);
preview_rules(overrides,expected_revision)→candidate+serial+clamps; apply_rules(preview).
ProjectActions.place_card/copy_token/actor_inventory/actor_placements/delete_actor;
MapsService.commit_placements/record_operation — публичная адресованная история.
Напрямую подменять Actor owner/refs нельзя и через EntityCollection.put_payload.

Undo создания хранит receipt только созданного Actor/inventory/default и token delta;
независимый input не восстанавливается из whole-map/Card snapshot. Внешние refs/правки
блокируют inverse до index change. Обычный delete last placement state не удаляет.
Перmanent NPC возможно сохранить без placement, но ordinary player=false placement
по согласованному контракту создаёт нового; отдельный shared-NPC UX отложен.

Доработки не меняют production dependencies/стек. Полный snapshot/синхронный backup
сохраняют известную стоимость, без попытки скрыть её вторым writer/каноном.

## Дополнение UI-приёмки — ADR-034

Владелец заменил Inspector-only игровой ввод системными страницами Card Editor.
Адресация, Actor/Token, вычисления, HP clamp, persistence и формат этого ADR сохранены.
Правила открываются из gear, Item modifiers — компактный список/typed dialog.
Подробности: ADR-034 и validation/2026-11-21-ui-acceptance-fix.md.


## Дополнение 22.11.2026 — ADR-035

Лист v2 и equipment facts заменяют сохранённую броню/щит Card и прежние proficiency
формы. Новый SQLite16/Card7/profile2 по прямому разрешению владельца «все миры тестовые»;
миграций/legacy нет, старые файлы отклоняются без записи. Actor/Token ownership,
FieldEdits, native document lifecycle и функциональные границы сохранены.
Generic Tables cell hooks собирает composition root; pure EquipmentFacts и профиль —
Cards. AST105modules/264edges/0cycles, gate не ослаблен. Подробности и критерии1–7:
docs/validation/2026-11-22-character-sheet-v2.md.
