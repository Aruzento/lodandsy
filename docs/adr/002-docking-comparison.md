# ADR-002: сравнение оконной инфраструктуры

Статус: W2 принят, обязательный ручной preflight пройден владельцем 18.11.2026,
production мигрирован. ARU-55, ARU-19/23/24/25/32, ARU-56/57.

Итог: PySide6/shiboken6 6.11.2 и PySide6-QtAds 5.1.1 зафиксированы в pyproject и lock.
Владелец подтвердил запуск без Python, направления/CENTER/insert/float/redock,
maximize→drag без прыжка точки захвата, независимые Cards, restart layout,
перенос между мониторами и mixed DPI. Это ручные результаты владельца, не offscreen.
DLL-сбой первого frozen build устранён: несовместимая ICU78 исключена из spec,
Qt использует системную ICU Windows. Production source и frozen MVP smoke проходят.

WorkspaceHost (CDockManager) — единственный владелец layout. WindowManager хранит
registry, focus и lifecycle, закрытие освобождает только нужный документ. Tree,
Inspector и rails — фиксированные элементы AppShell. Domain не импортирует ADS/Qt.
Старые workspace_dock/workspace_drop_overlay и их внутренние тесты удалены после
замены регрессиями публичных сценариев ADS/lifecycle/независимости документов.

UI хранится отдельно от мира в `.lodandsy-ui.json`: version, document keys, active,
Tree selection/expanded, Card cursor/scroll/mode, Map camera, native geometry и ADS
state. Сначала создаются документы по стабильным ключам, затем восстанавливается
раскладка. Пропавший документ даёт безопасные вкладки; недоступные экраны — clamp.
Повреждённый/будущий UI-файл диагностируется и сохраняется перед заменой. Нет SQL
payload в UI state. Undo не переносится между запусками.

Сквозная функциональная приёмка полной сборки подтверждена владельцем 18.11.2026,
включая совместную работу документов и восстановление после перезапуска.
Ограничение поставки: полная сборка пока проверена с Python, clean-Windows проверка
остаётся открытой; успешный W2 preflight без Python относится к предыдущему артефакту.
Пересмотр: несовместимый wheel/Qt, провал обязательного оконного сценария или сборки.

Ниже — исторические результаты сравнения до принятия W2; упоминания запрета миграции
и неизменённого production описывают тот этап, а не текущее состояние.

Контекст: AppShell уже содержит собственную обработку drag/drop поверх QDockWidget.
Расширять её до insert, native maximize→drag и mixed DPI без сравнения запрещено
контрактом. Требуются фиксированные Tree/Inspector и независимые рабочие документы.

Варианты:

- Текущий код: два CENTER дают целевую центральную область 0×0; дефект ARU-32
  воспроизведён. Документы существуют, но target вычисляется по схлопнутому виджету.
- W1: штатный QMainWindow/QDockWidget без пустого centralWidget. Структурный прототип
  выполняет tab, split, float, maximize/restore, saveState/restoreState и close/reopen.
  Последовательность операций важна: первоначальная попытка split после tab потеряла
  ожидаемую tab-связь; вариант split перед tab проходит. Это не доказательство, что
  интерактивный insert и preview будут удовлетворять продуктовому контракту.
- W2: Qt ADS через PySide6-QtAds 5.1.1. Структурный прототип выполняет те же сценарии,
  содержит три dock-area; floating — top-level окно без FramelessWindowHint.
  Это проверка флагов/API, а не приёмка системного заголовка или Windows snap мышью.
- W3 KDDockWidgets пока не нужен: W1 и W2 пригодны для следующей проверки.

Фактическая совместимость 18.11.2026: Python 3.14.8 x64, PySide6/shiboken6 6.11.2.
Wheel 5.1.1 (cp310-abi3-win_amd64) требует ровно PySide6-Essentials/shiboken6 6.11.2,
импортируется и проходит прототип. Более свежий 5.1.1.1 требует 6.12.0 и с текущим
окружением выдаёт DLL load failed: procedure not found. Установлены только
изолированные копии в .prototype-deps; pyproject и рабочее .venv не изменены.
METADATA и файл лицензии указывают LGPL v2.1 для Qt ADS/bindings (отдельные части MIT).
Обязательства дистрибутива необходимо проверить при упаковке; юридическое заключение
не делалось.

Доказательства и команды:

```powershell
.\.venv\Scripts\python.exe -m prototypes.docking_compare --backend current
.\.venv\Scripts\python.exe -m prototypes.docking_compare --backend native
.\.venv\Scripts\python.exe -m prototypes.docking_compare --backend ads
```

Все три прогона завершены на Qt platform=windows. Для ручной проверки добавьте --show.
Для воспроизведения W2 без изменения зависимостей приложения:

```powershell
.\.venv\Scripts\python.exe -m pip download --only-binary=:all: --no-deps --dest .prototype-deps PySide6-QtAds==5.1.1
.\.venv\Scripts\python.exe -m pip install --no-deps --no-index --target .prototype-deps/qt611 .prototype-deps/pyside6_qtads-5.1.1-cp310-abi3-win_amd64.whl
```

Предложение: W2 как кандидат на раннюю Windows-сборку и ручную приёмку, затем
интеграция при прохождении сценариев. Он уменьшает объём собственной инфраструктуры,
но связывает обновления Qt с совместимым wheel ADS. W1 остаётся вариантом без новой
зависимости; потребуется доказать interactive insert и соответствие drop preview.
До решения W1/W2 текущий docking не заменяется и не расширяется.

Ограничения доказательств: не проверены drag/insert/Escape мышью, захват maximized окна,
два монитора, mixed DPI, восстановление при исчезновении экрана и установленный build.
Native UI доступен через accessibility, но Windows capture вернул FrameArrived timeout
и window capture timeout после повторного подключения. Полная ручная приёмка не пройдена.
Условие пересмотра: провал ручного сценария/упаковки либо отсутствие совместимого wheel.

Первичные источники (прочитаны 18.11.2026):
[Qt 6.11 QMainWindow](https://doc.qt.io/qt-6.11/qmainwindow.html),
[Qt ADS user guide](https://github.com/githubuser0xFFFF/Qt-Advanced-Docking-System/blob/master/doc/user-guide.md),
[bindings на PyPI](https://pypi.org/project/PySide6-QtAds/),
[исходный код floating](https://github.com/githubuser0xFFFF/Qt-Advanced-Docking-System/blob/master/src/FloatingDockContainer.cpp).


Условия владельца перед миграцией: дистрибутив без установленного Python; docking
во всех направлениях/CENTER/insert/float/redock; maximize→drag с сохранением точки
захвата; независимые редакторы без потери данных; layout roundtrip, DPI/несколько
мониторов; совместимые версии и лицензии. После успеха миграция разрешена автономно,
заменённая реализация удаляется после проверки регрессий. Fixed panels/rails сохраняются,
ADS владеет layout, WindowManager — lifecycle, domain не зависит от ADS.

Изолированный прототип с реальными Card Editor: prototypes/ads_cards_spike.py;
запуск из prototypes/w2_launcher.py, упаковщик 6.22.3 и hooks 2026.10. Версии фиксированы
в prototypes/requirements-w2-preflight.txt. PyInstaller успешно собирает onedir,
но первый frozen smoke выявил DLL load failed, в том числе при загрузке QtCore;
одна сборка ещё не доказывает работоспособность. Локальный source self-test проходит:
правки A/B при программном перемещении, float/maximize/redock, layout roundtrip,
fixed panels, close/reopen Undo. Обнаружено два монитора по 1920×1080, DPR=1, DPI=96;
mixed DPI и drag мышью не проверены. Production docking пока не заменён.
