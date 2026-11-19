# ADR-010 — встроенные Markdown templates

19.11.2026, ARU-74. Card остаётся универсальным документом. Реестр domain
`CardTemplate(id,title,version,content)` содержит пять immutable записей версии1:
empty/article/character/location/item. Нет Qt, SQL, правил D&D и нового entity kind.
Имя и шаблон выбираются в одном диалоге из plus menu или дочернего context menu.
Session проверяет template ID до mutation и создаёт Card с content одним событием.
Пустая карточка имеет пустой source; неизвестный ID — ошибка без частичных записей.
Parent/order/UUID проверяются прежней моделью. Каждая Card получает самостоятельный
текст, обновление реестра не меняет существующие карточки. Template provenance в
проект не записывается: не нужен для интерпретации Markdown, миграции SQLite нет.

Применение к существующей Card и пользовательский registry за пределами этого блока.
Случайный overwrite невозможен: команда доступна только при создании. Для будущего
обмена template.content — обычный Markdown; импорт/экспорт не требует plugin runtime.
Тесты: пять create/edit/save/reopen, root/child/cancel, atomic unknown ID, независимость
копий, совместимость source со ссылками/изображениями. Native dialog/focus — итоговая
ручная проверка. Пересмотр при появлении утверждённого пользовательского registry.
