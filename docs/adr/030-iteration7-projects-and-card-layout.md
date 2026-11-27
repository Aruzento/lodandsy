# ADR-030 — каталог проектов и обязательная компоновка Card Editor

Принято владельцем в пакете итерации7 и дополнении 20.11.2026. Заменяет
противоречащие решения ADR-021/029: MOW удалён, тип Card после создания неизменяемый,
breadcrumb, summary popup и центрированная колонка текста отменены.

## Проекты

Историческое решение. Управляемый каталог и правила v0.01 определяет
[ADR-040](040-managed-projects-v001.md). Контракт Card Editor ниже действует.

Единственный владелец переключения — ProjectController. Welcome и команда Open
показывают пассивный каталог известных проектов, затем позволяют выбрать другую папку.
Автоматического открытия последнего мира нет. QSettings с явной идентичностью
LODANDSY/LODANDSY хранит MRU title/path и последнюю папку диалога вне мира/backup.
Только успешные create/open/restore добавляют запись. Windows case-insensitive
absolute identity исключает дубли. Удаление записи не удаляет файлы; locate заменяет
старый адрес только после успешного открытия. Старт не сканирует каталоги проектов.
Неудачное открытие сохраняет текущий проект. Dirty/drafts проходят прежний guard.
Резервное копирование и восстановление доступны из gear правого rail; дубли меню удалены.

MOW parser/controller/actions/worker hooks и специальные поля удаляются полностью.
Общие aliases, HTML sanitation, ресурсы и типы Card сохраняются. SQLite14/Card5
явно отклоняют предыдущий формат без записи. Пользовательские файлы не удаляются.

## Card Editor

Обязательная структура Qt Widgets: квадратный портрет слева 132–220 logical px;
справа read-only type badge, крупное единственное название, inline summary.
Ниже самостоятельный ряд вкладок и контент с общим левым отступом16 px.
Copy link остаётся в контекстном меню и Tree. Никаких breadcrumb/summary popup.
Геометрия header зависит от ширины, а не содержимого, активности, высоты или вкладки.
QTextDocument и семантические буферы остаются непрерывными; UI не пересоздаёт данные.
CardCollection запрещает смену типа; CardPayload проверяет replacement через
минимальный generic hook EntityCollection, включая прямой put_payload.

Целевые проверки A:31 passed. B:47 прежних regression checks прошли; четыре новых
проверки immutable type/геометрии прошли на Windows QPA. Ручная оценка интерфейса
и нескольких мониторов учитывается отдельно в итоговом чек-листе.


Welcome — самостоятельный top-level Qt.Window без скрытого QWidget parent; иначе
Windows/automation не получают нормального самостоятельного стартового окна.
New folder dialog использует видимый chooser как host, ошибка создания показывается
в нём inline. Обычный Open chooser остаётся модальным к видимому AppShell.
Это проверено native Welcome cancel/fail/success tests; ручной capture учитывается отдельно.

## Дополнение 21.11.2026 — ADR-033

Действующий формат SQLite15/Card6/Map7/Actor1/Rules1/Table3/UIstate4. Schema14
безопасно отклоняется без миграции/записи. Guards ProjectController/MRU/backup
сохраняются. Card Editor header/type/layout не меняется; relations-purpose rich
section дополнена адресованным списком Actor, включая без размещений.
