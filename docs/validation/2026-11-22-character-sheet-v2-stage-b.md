> Архив промежуточного состояния. После этого владелец разрешил отказ от старых тестовых миров; ADR-035 и итоговый отчёт отменяют ожидание решения ниже.

# Лист персонажа v2 — промежуточный результат A/B и граница совместимости

22.11.2026. Пакет целиком ещё не завершён. Экипировка/новый формат и финальный Windows
кандидат ожидают решения владельца о существующих мирах SQLite15. Ни один реальный
мир не открывался и не изменялся. Commit/push/merge/release не выполнялись.

## Исходное состояние

Прочитан C:/Users/Aruko/Downloads/LODANDSY_character_sheet_v2.md целиком. Фактический
HEAD/local origin ref fee0106e6fc9177db3438332d83a3cd46a75d4a7, ветка
codex/ui-acceptance-fix; tracked tree до работы чистый, четыре private untracked
сохранены. [CI44950034132](https://github.com/Aruzento/lodandsy/actions/runs/44950034132)
для этого коммита completed/success проверен через gh run list. Полный baseline не
повторялся. ARU-65/80/83 In Progress, ARU-84 Done; последние замечания 22.11 прочитаны.

Прочитаны AGENTS/START, ADR-033/034; изучены card_schema, Card/CardPayload, calculate/
ProjectRules, inventory_inputs/validate_project, CardsService/ProjectActions, Tables
cell write path, SQLite store/codecs и native sheet/bindings. Новый ADR-035 фиксирует
предлагаемый единственный источник экипировки и конкретные варианты перехода.

## Референсы

Изучены [Long Story Short: снимок листа](https://longstoryshort.app/doc/vortex/adding-characters/),
[бонусы](https://longstoryshort.app/doc/character-sheet/bonuses/) и
[контракт](https://longstoryshort.app/doc/developers/characters/).
Публичный снимок листа просмотрен локально в исследовательском кеше; в приложение,
репозиторий или сборку не включается. Применены группировка по характеристикам,
краткие строки владение/название/итог и детали показателей по нажатию. Слои бонусов
внешнего сервиса не заменяют существующий порядок нашего движка.

Открыты [D&D Beyond players](https://www.dndbeyond.com/en/players),
[sheet revamp](https://www.dndbeyond.com/posts/262-the-character-sheet-revamp-is-live-now),
[Foundry AC fields](https://github.com/foundryvtt/dnd5e/wiki/Roll-Formulas),
[Basic Rules2014 equipment](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/equipment),
[создание персонажа](https://www.dndbeyond.com/sources/dnd/basic-rules-2014/step-by-step-characters),
[русская терминология характеристик](https://5e14.dnd.su/articles/newbie/468-using-ability-scores/)
и [снаряжения](https://dnd.su/articles/inventory/147-armor-arms-equipment-tools/).
Aether Keep недоступен: www host timeout, https://aetherkeep.com/ HTTP403; его
компоновка не выдана за изученную. Чужие справочники/код/изображения не импортировались.

## Выполненный независимый UI блок

- ability_block.py: шесть блоков, первая строка — спасбросок, затем свои skills;
  18 навыков/6 спасбросков, без старых dropdown и отдельных повторных «Итог».
  ○/●/◆ означают0/1/2, имеют русские accessible names/tooltips; сохранение через
  существующий binding/FieldEdits. В Actor контексте владение наследуется read-only.
- Inline SemanticLineEdit рядом с модификатором постоянно доступен в базовом контексте.
  Actor видит effective score, базу и происхождение; кнопка «К базе» переключает явно.
  Enter/Tab/blur/Escape и конфликтная политика не заменены новым edit manager.
- Native header race/class/level с редактируемыми подсказками, своим текстом/unknown.
  Архетип предусмотрен в виджете, но не подключён к FieldDefinition до решения нового
  контракта. Это ещё не выполнение всей группы критериев3.
- Resource strip уплотнён: current/max/temp, единый AC, initiative/speed/proficiency.
  HP и speed settings раскрываются по нажатию; AC открывает отдельный native dialog
  с адресованным manual input. Полный equipment breakdown подключается в блоке C/D.
  Прежние Card armor facts пока остаются действующими: формат/семантика не изменены.
- 3/2/1 ability columns по viewport. Узкий контекст перенесён на отдельную строку,
  поля не требуют горизонтального scroll. Исправлены clipping вложенного QLineEdit
  в editable combo и слишком бледные read-only индикаторы. Никакого web runtime.
- Base inventory navigation не создаёт Actor или Table при просмотре; явная команда
  создания работает по прежнему пути. Actor inventory остаётся адресованным.
- domain/equipment.py: изолированный pure DTO/resolver с проверкой типов, отсутствующих
  определений и конфликта двух слотов. Он пока не подключён к канону/профилю: никакого
  второго пути начисления КД в runtime не добавлено.

## Фактические проверки

CPython3.14.8 из .prototype-deps/locked-venv/Scripts/python.exe, QPA windows.

```powershell
python -m pytest -q tests/test_character_sheet_v2_ui.py tests/test_game_sheet_ui.py tests/test_semantic_input.py tests/test_actor_inspector.py tests/test_module_boundaries.py -p no:cacheprovider
python -m ruff check .
python -m pip check
git diff --check
python -m prototypes.architecture_graph --report .prototype-deps/character-sheet-v2/imports-stage-b.json
```

Последний target:37passed/8.67s; Ruff/pip/diff проходят (только Git LF→CRLF warning).
AST105modules/260edges/0cycles; четыре helpers явно Cards-owned, запреты не ослаблены.
Проверены ХАР13/БМ3→+1/+4/+7, save+1/+4, inlineDEX14→16 и зависимые результаты, Escape,
native focus после commit, header homebrew, manual Card/Actor AC и закрытие диалога
при смене участника. Existing semantic/Inspector/conflict/width gates входят в target.

Production Qt QWidget.grab снимки делались после реального layout в disposable world
и осматривались: обычное окно1450×1000, карточки1040/660/400, Object/Item, native AC
dialog420×321, карта с оперативным Inspector. Исправления сделаны после просмотра,
не только по widget metadata. Локальные материалы:

- .prototype-deps/character-sheet-v2/stage-b-views/01-character-workspace.png
- .prototype-deps/character-sheet-v2/stage-b-views/04-character-narrow.png
- .prototype-deps/character-sheet-v2/stage-b-views/12-ac-details-stage.png
- .prototype-deps/character-sheet-v2/stage-b-views/11-map-inspector.png

Дополнительные production рендеры QT_SCALE_FACTOR1.25/1.5/2 прошли и осмотрены;
метаданные подтверждают фактический DPR1.25/1.5/2. Материалы находятся в stage-b-dpr*. Это не physical mixed DPI.
Computer-use и Browser-use не инициализировались: `failed to write kernel assets:
Системе не удается найти указанный путь. (os error 3)`. Снимки Qt не названы desktop
capture, ручной приёмкой, двумя физическими мониторами или clean Windows.

## Почему остановлен блок C

В SQLite15/Card6 armor_type/armor_base/shield сохранены в Card; calculate добавляет
старый shield source. Template inventory не имеет active, owned Actor inventory имеет.
Просто удалить поля и считать из пустой экипировки означает изменить существующие
автоматические КД и пользовательские формулы. Сохранить оба источника противоречит
требованию единственного канона. Новое задание прямо отменяет допущение о потере данных
текущих миров: §3 «если нужен выбор владельца о несовместимости, остановиться именно
на этой границе, подготовив варианты». Поэтому storage/schema/codecs/profile не менялись.

ADR-035 предлагает:

1. Явный перенос в новую копию: исходник read-only, прежние UUID/данные/refs сохраняются,
   прежние armor facts переводятся в явно помеченные Item + active inventory rows;
   custom formulas/effective values проверяются, неожиданное изменение блокирует запись.
2. Без переноса: новая версия явно отклоняет SQLite15 без записи; старые миры доступны
   прежней сборкой, новый формат создаёт только новые миры. Это требует отдельного
   выбора владельца именно для SQLite15, не ссылки на исторический отказ от schema14.

Вопрос отправлен владельцу, ответа пока нет. Зависимые изменения не выполняются.
До ответа нет нового EXE/ZIP, финального full/offscreen gate или заявления о выполнении
всех критериев1–7. Предыдущий ZIP остаётся предыдущим кандидатом, не листом v2.

## Дальнейшие шаги после выбора

Закрепить политику/версии ADR-035, подключить subclass и типизированные Item поля;
resolver только активного инвентаря и один armor/shield; final validator всех путей,
explicit atomic replace/cancel со stale guard; resolved inputs в rules без Card shield;
совместимость формул, manual final/source breakdown в диалоге. Затем AC матрица 5e14,
индивидуальность Actor/shared Player, persistence/backup/old-file safety, UI focus и
визуальная итерация, один full native/offscreen/Ruff/pip/AST gate, EXE/parity и
source/frozen/portable smoke. Новый ZIP/SHA и итоговый отчёт только после этого.

ARU-65/80/83 остаются In Progress, ARU-84 Done. Новых задач и Git-публикаций нет.
